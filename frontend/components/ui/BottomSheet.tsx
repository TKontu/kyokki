'use client';

import React, { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useT } from '@/lib/i18n';

export interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  /** Close when the dimmed backdrop is tapped. Default true. */
  closeOnBackdrop?: boolean;
  className?: string;
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

function focusableIn(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
}

/*
 * The body scroll lock, shared by every open sheet.
 *
 * `overflow: hidden` on the body alone does not stop iOS Safari from scrolling the page on
 * touch, so a drag on the backdrop, or past the end of a sheet's own scroll area, used to move
 * the page behind the sheet (operator, 2026-10-07: "touching the screen scrolls the
 * background"). Pinning the body with `position: fixed` at the current scroll offset is what
 * holds it still there; the page goes back to that offset on unlock.
 *
 * Ref-counted, because sheets can be open together or swap in one render (the item sheet hands
 * over to the product's sheet): each sheet saving and restoring the body on its own restored a
 * stale value whenever they closed out of order - an outer sheet closing first left the inner
 * one to "restore" `overflow: hidden` for good. Now the first lock saves the body as it was,
 * the last unlock restores exactly that, and nothing in between touches it.
 */
const LOCKED_PROPS = ['overflow', 'position', 'top', 'left', 'right', 'width'] as const;
type LockedProp = (typeof LOCKED_PROPS)[number];

let lockCount = 0;
let savedBody: { style: Record<LockedProp, string>; scrollY: number } | null = null;

function lockBody(): void {
  lockCount += 1;
  if (lockCount > 1) return;
  const { style } = document.body;
  const scrollY = window.scrollY;
  savedBody = {
    style: Object.fromEntries(LOCKED_PROPS.map((prop) => [prop, style[prop]])) as Record<
      LockedProp,
      string
    >,
    scrollY,
  };
  style.overflow = 'hidden';
  style.position = 'fixed';
  style.top = `-${scrollY}px`;
  style.left = '0';
  style.right = '0';
  style.width = '100%';
}

function unlockBody(): void {
  if (lockCount === 0) return;
  lockCount -= 1;
  if (lockCount > 0 || !savedBody) return;
  const { style } = document.body;
  for (const prop of LOCKED_PROPS) style[prop] = savedBody.style[prop];
  // An emptied style attribute is removed, so the body is left exactly as it was found
  if (style.length === 0) document.body.removeAttribute('style');
  // Unpinning drops the page to the top; put it back where the sheet found it
  if (savedBody.scrollY > 0) window.scrollTo(0, savedBody.scrollY);
  savedBody = null;
}

const BottomSheet: React.FC<BottomSheetProps> = ({
  open,
  onClose,
  title,
  children,
  footer,
  closeOnBackdrop = true,
  className = '',
}) => {
  const [mounted, setMounted] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const { t } = useT();

  // Keep the latest onClose without re-running the open effect on every render.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open || !mounted) return;
    const panel = panelRef.current;
    if (!panel) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    lockBody();

    // The action the sheet is named after, when it says which it is: focus used to land on the
    // ✕, and the primary sits past every field in the form (H45). A destructive sheet marks its
    // *safe* control instead, so Enter never throws food away.
    // `:not([disabled])` matters: Save starts disabled until something changes, and focusing a
    // disabled button silently leaves focus on the body, outside the trap.
    const primary = panel.querySelector<HTMLElement>('[data-primary]:not([disabled])');
    (primary ?? focusableIn(panel)[0] ?? panel).focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab') return;

      const focusables = focusableIn(panel);
      if (focusables.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      const outside = !panel.contains(active);

      if (event.shiftKey && (active === first || outside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || outside)) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);

    return () => {
      document.removeEventListener('keydown', onKeyDown);
      unlockBody();
      if (previouslyFocused && document.contains(previouslyFocused)) {
        previouslyFocused.focus();
      }
    };
  }, [open, mounted]);

  // A drag that starts on the dim backdrop itself has nothing to scroll: cancel it, so iOS does
  // not hand it to the page. Not passive, or preventDefault is ignored. A drag inside the panel
  // is left alone; its scroll area contains its own overscroll.
  const backdropRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open || !mounted) return;
    const backdrop = backdropRef.current;
    if (!backdrop) return;
    const onTouchMove = (event: TouchEvent) => {
      if (event.target === backdrop) event.preventDefault();
    };
    backdrop.addEventListener('touchmove', onTouchMove, { passive: false });
    return () => backdrop.removeEventListener('touchmove', onTouchMove);
  }, [open, mounted]);

  if (!open || !mounted) return null;

  const panelClassName = `
    flex w-full max-w-2xl max-h-[85vh] flex-col
    rounded-t-ui-lg border border-b-0
    bg-white dark:bg-ui-dark-bg
    border-ui-border dark:border-ui-dark-border
    shadow-ui-md dark:shadow-ui-dark-md
    focus:outline-none
    animate-sheet-up motion-reduce:animate-none
    ${className}
  `
    .trim()
    .replace(/\s+/g, ' ');

  return createPortal(
    <div
      ref={backdropRef}
      data-testid="bottom-sheet-backdrop"
      // touch-none: no pan or zoom starts on the backdrop (the panel's scroll area is its own
      // scroll container, so it still pans); overscroll-contain: nothing chains to the page.
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/40 touch-none overscroll-contain"
      onClick={(event) => {
        if (closeOnBackdrop && event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={panelClassName}
      >
        <div className="flex items-center justify-between gap-2 border-b border-ui-border dark:border-ui-dark-border pl-4 pr-1 py-1">
          <h2 id={titleId} className="text-lg font-semibold text-ui-text dark:text-ui-dark-text">
            {title}
          </h2>
          <button
            type="button"
            aria-label={t('common.close')}
            onClick={onClose}
            className="min-h-touch min-w-touch rounded-ui text-ui-text-secondary dark:text-ui-dark-text-secondary hover:bg-ui-bg-secondary dark:hover:bg-ui-dark-bg-secondary transition-all duration-ui focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 no-select"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto overscroll-contain touch-pan-y px-4 py-4">
          {children}
        </div>
        {footer && (
          <div className="border-t border-ui-border dark:border-ui-dark-border px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
            {footer}
          </div>
        )}
        {!footer && <div className="pb-[env(safe-area-inset-bottom)]" />}
      </div>
    </div>,
    document.body
  );
};

export default BottomSheet;
