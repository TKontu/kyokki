'use client';

import React, { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

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
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

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
      document.body.style.overflow = previousOverflow;
      if (previouslyFocused && document.contains(previouslyFocused)) {
        previouslyFocused.focus();
      }
    };
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
      data-testid="bottom-sheet-backdrop"
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/40"
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
            aria-label="Close"
            onClick={onClose}
            className="min-h-touch min-w-touch rounded-ui text-ui-text-secondary dark:text-ui-dark-text-secondary hover:bg-ui-bg-secondary dark:hover:bg-ui-dark-bg-secondary transition-all duration-ui focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 no-select"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">{children}</div>
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
