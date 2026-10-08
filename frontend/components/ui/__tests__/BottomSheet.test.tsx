import React, { useState } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import BottomSheet from '../BottomSheet';

function Harness({
  closeOnBackdrop,
  onClose,
}: {
  closeOnBackdrop?: boolean;
  onClose?: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button onClick={() => setOpen(true)}>Open sheet</button>
      <BottomSheet
        open={open}
        title="Consume item"
        closeOnBackdrop={closeOnBackdrop}
        onClose={() => {
          onClose?.();
          setOpen(false);
        }}
      >
        <button>First action</button>
        <button>Last action</button>
      </BottomSheet>
    </div>
  );
}

function openSheet() {
  const trigger = screen.getByRole('button', { name: 'Open sheet' });
  trigger.focus();
  fireEvent.click(trigger);
  return trigger;
}

describe('BottomSheet', () => {
  describe('Rendering', () => {
    it('renders nothing when closed', () => {
      render(
        <BottomSheet open={false} title="Hidden" onClose={() => {}}>
          <p>content</p>
        </BottomSheet>
      );
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(screen.queryByText('content')).not.toBeInTheDocument();
    });

    it('renders a modal dialog named by its title when open', () => {
      render(
        <BottomSheet open title="Consume item" onClose={() => {}}>
          <p>content</p>
        </BottomSheet>
      );
      const dialog = screen.getByRole('dialog', { name: 'Consume item' });
      expect(dialog).toHaveAttribute('aria-modal', 'true');
      expect(screen.getByText('content')).toBeInTheDocument();
    });

    it('renders into document.body through a portal', () => {
      const { container } = render(
        <BottomSheet open title="Portal" onClose={() => {}}>
          <p>content</p>
        </BottomSheet>
      );
      expect(container).toBeEmptyDOMElement();
      expect(document.body).toContainElement(screen.getByRole('dialog'));
    });

    it('rests at its final position without waiting for an animation frame', () => {
      // Hidden tabs and resuming PWAs pause requestAnimationFrame; the slide-up must be
      // decoration only, never a precondition for the sheet being on screen.
      const raf = jest.spyOn(window, 'requestAnimationFrame').mockImplementation(() => 0);
      render(
        <BottomSheet open title="Frame" onClose={() => {}}>
          <p>content</p>
        </BottomSheet>
      );
      const dialog = screen.getByRole('dialog');
      expect(dialog.className).not.toContain('translate-y-full');
      expect(dialog.className).toContain('animate-sheet-up');
      expect(dialog.className).toContain('motion-reduce:animate-none');
      raf.mockRestore();
    });

    it('renders an optional footer', () => {
      render(
        <BottomSheet open title="Footer" onClose={() => {}} footer={<button>Confirm</button>}>
          <p>content</p>
        </BottomSheet>
      );
      expect(screen.getByRole('button', { name: 'Confirm' })).toBeInTheDocument();
    });
  });

  describe('Closing', () => {
    it('closes on Escape', () => {
      const onClose = jest.fn();
      render(<Harness onClose={onClose} />);
      openSheet();

      fireEvent.keyDown(document, { key: 'Escape' });

      expect(onClose).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('closes on backdrop click', () => {
      const onClose = jest.fn();
      render(<Harness onClose={onClose} />);
      openSheet();

      fireEvent.click(screen.getByTestId('bottom-sheet-backdrop'));

      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('does not close when clicking inside the panel', () => {
      const onClose = jest.fn();
      render(<Harness onClose={onClose} />);
      openSheet();

      fireEvent.click(screen.getByRole('dialog'));
      fireEvent.click(screen.getByRole('button', { name: 'First action' }));

      expect(onClose).not.toHaveBeenCalled();
    });

    it('ignores backdrop clicks when closeOnBackdrop is false', () => {
      const onClose = jest.fn();
      render(<Harness onClose={onClose} closeOnBackdrop={false} />);
      openSheet();

      fireEvent.click(screen.getByTestId('bottom-sheet-backdrop'));

      expect(onClose).not.toHaveBeenCalled();
    });

    it('closes from a 44pt close button', () => {
      const onClose = jest.fn();
      render(<Harness onClose={onClose} />);
      openSheet();

      const close = screen.getByRole('button', { name: 'Close' });
      expect(close.className).toContain('min-h-touch');
      expect(close.className).toContain('min-w-touch');
      fireEvent.click(close);

      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  describe('Focus management', () => {
    it('moves focus into the dialog on open', () => {
      render(<Harness />);
      openSheet();

      expect(screen.getByRole('dialog')).toContainElement(document.activeElement as HTMLElement);
    });

    it('lands on the action the sheet is for, not the close button', () => {
      // On a tablet the cook opens a sheet to do the thing it is named after; a keyboard or a
      // switch lands on ✕ otherwise, and the primary sits past everything in the form (H45).
      render(
        <BottomSheet open onClose={jest.fn()} title="Quick add">
          <input aria-label="Name" />
          <button data-primary>Add</button>
        </BottomSheet>
      )

      expect(document.activeElement).toHaveTextContent('Add')
    })

    it('falls back when the primary is disabled, rather than focusing nothing', () => {
      render(
        <BottomSheet open onClose={jest.fn()} title="Edit">
          <input aria-label="Quantity" />
          <button data-primary disabled>
            Save
          </button>
        </BottomSheet>
      )

      expect(document.activeElement).toHaveAttribute('aria-label', 'Close')
    })

    it('falls back to the first focusable when nothing claims to be primary', () => {
      render(
        <BottomSheet open onClose={jest.fn()} title="Plain">
          <input aria-label="Name" />
        </BottomSheet>
      )

      expect(document.activeElement).toHaveAttribute('aria-label', 'Close')
    })

    it('wraps Tab from the last focusable element to the first', () => {
      render(<Harness />);
      openSheet();
      const focusables = screen.getByRole('dialog').querySelectorAll('button');
      const first = focusables[0];
      const last = focusables[focusables.length - 1];

      last.focus();
      fireEvent.keyDown(document, { key: 'Tab' });

      expect(document.activeElement).toBe(first);
    });

    it('wraps Shift+Tab from the first focusable element to the last', () => {
      render(<Harness />);
      openSheet();
      const focusables = screen.getByRole('dialog').querySelectorAll('button');
      const first = focusables[0];
      const last = focusables[focusables.length - 1];

      first.focus();
      fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });

      expect(document.activeElement).toBe(last);
    });

    it('returns focus to the trigger on close', () => {
      render(<Harness />);
      const trigger = openSheet();

      fireEvent.keyDown(document, { key: 'Escape' });

      expect(document.activeElement).toBe(trigger);
    });
  });

  describe('Scroll lock', () => {
    it('locks body scroll while open and restores it after close', () => {
      document.body.style.overflow = 'auto';
      render(<Harness />);
      openSheet();

      expect(document.body.style.overflow).toBe('hidden');

      fireEvent.keyDown(document, { key: 'Escape' });

      expect(document.body.style.overflow).toBe('auto');
      document.body.style.overflow = '';
    });

    // iOS Safari scrolls the page behind an overflow:hidden body on touch (operator,
    // 2026-10-07: "touching the screen scrolls the background"). Pinning the body with
    // position:fixed is what actually holds it still there.
    describe('iOS-safe lock', () => {
      let scrollTo: jest.SpyInstance;

      beforeEach(() => {
        document.body.removeAttribute('style');
        scrollTo = jest.spyOn(window, 'scrollTo').mockImplementation(() => {});
        Object.defineProperty(window, 'scrollY', { value: 320, configurable: true });
      });
      afterEach(() => {
        scrollTo.mockRestore();
        Object.defineProperty(window, 'scrollY', { value: 0, configurable: true });
        document.body.removeAttribute('style');
      });

      function Sheet({ title, open = true }: { title: string; open?: boolean }) {
        return (
          <BottomSheet open={open} title={title} onClose={() => {}}>
            <button>{`In ${title}`}</button>
          </BottomSheet>
        );
      }

      function Two({ outer, inner }: { outer: boolean; inner: boolean }) {
        return (
          <>
            <Sheet title="Outer" open={outer} />
            <Sheet title="Inner" open={inner} />
          </>
        );
      }

      it('pins the body where the page was, and puts the page back on close', () => {
        document.body.style.position = 'relative';
        const { rerender } = render(<Sheet title="One" />);

        expect(document.body.style.position).toBe('fixed');
        expect(document.body.style.top).toBe('-320px');
        expect(document.body.style.width).toBe('100%');
        expect(document.body.style.overflow).toBe('hidden');

        rerender(<Sheet title="One" open={false} />);

        expect(document.body.style.position).toBe('relative');
        expect(document.body.style.top).toBe('');
        expect(document.body.style.width).toBe('');
        expect(document.body.style.overflow).toBe('');
        expect(scrollTo).toHaveBeenCalledWith(0, 320);
      });

      it('nested sheets lock once and restore the body exactly when the last closes', () => {
        const { rerender } = render(<Two outer inner={false} />);
        rerender(<Two outer inner />);
        expect(document.body.style.position).toBe('fixed');
        expect(document.body.style.top).toBe('-320px');

        rerender(<Two outer inner={false} />);
        // The outer one is still open: still locked, at the same place
        expect(document.body.style.position).toBe('fixed');
        expect(document.body.style.top).toBe('-320px');
        expect(scrollTo).not.toHaveBeenCalled();

        rerender(<Two outer={false} inner={false} />);
        expect(document.body.getAttribute('style') ?? '').toBe('');
        expect(scrollTo).toHaveBeenCalledTimes(1);
        expect(scrollTo).toHaveBeenCalledWith(0, 320);
      });

      it('closing the outer sheet first still unlocks once the inner one closes', () => {
        const { rerender } = render(<Two outer inner />);

        rerender(<Two outer={false} inner />);
        expect(document.body.style.position).toBe('fixed');

        rerender(<Two outer={false} inner={false} />);
        expect(document.body.getAttribute('style') ?? '').toBe('');
        expect(scrollTo).toHaveBeenCalledTimes(1);
      });

      it('a sheet swapped for another in one render never leaves the body locked', () => {
        // What the item sheet does: its own sheet goes, the product's sheet comes, same commit
        const { rerender } = render(<Two outer inner={false} />);
        rerender(<Two outer={false} inner />);
        expect(document.body.style.position).toBe('fixed');
        expect(document.body.style.top).toBe('-320px');

        rerender(<Two outer={false} inner={false} />);
        expect(document.body.getAttribute('style') ?? '').toBe('');
      });

      it('unmounting while open unlocks', () => {
        const { unmount } = render(<Two outer inner />);
        unmount();

        expect(document.body.getAttribute('style') ?? '').toBe('');
        expect(scrollTo).toHaveBeenCalledWith(0, 320);
      });

      // The item sheet hands over to the product's sheet and back by *remounting*: a different
      // component in the same place, not one BottomSheet whose `open` flips (operator,
      // 2026-10-08: after saving the product "the below window gets stuck" on the iPad). The
      // page must stay pinned through the handover - unpinning it for a frame, then pinning it
      // again where iOS had scrolled it for the keyboard, is how the sheet came back offset.
      it('a sheet remounted in place of another keeps the page pinned', async () => {
        function Swap({ which }: { which: 'a' | 'b' }) {
          return which === 'a' ? <Sheet key="a" title="A" /> : <Sheet key="b" title="B" />;
        }
        const { rerender } = render(<Swap which="a" />);
        await screen.findByRole('dialog', { name: 'A' });
        scrollTo.mockClear();

        rerender(<Swap which="b" />);
        await screen.findByRole('dialog', { name: 'B' });

        // Never unpinned in between: unpinning is what puts the page back (`scrollTo`)
        expect(scrollTo).not.toHaveBeenCalled();
        expect(document.body.style.top).toBe('-320px');

        rerender(<></>);
        expect(document.body.getAttribute('style') ?? '').toBe('');
        expect(scrollTo).toHaveBeenCalledWith(0, 320);
      });
    });

    describe('touch', () => {
      it('the backdrop takes no pan and contains overscroll; the sheet body pans vertically', () => {
        render(
          <BottomSheet open title="Touch" onClose={() => {}}>
            <p>content</p>
          </BottomSheet>
        );
        const backdrop = screen.getByTestId('bottom-sheet-backdrop');
        expect(backdrop).toHaveClass('touch-none', 'overscroll-contain');
        const scroller = screen.getByText('content').parentElement as HTMLElement;
        expect(scroller).toHaveClass('overflow-y-auto', 'overscroll-contain', 'touch-pan-y');
      });

      it('a touchmove on the backdrop itself is cancelled', () => {
        render(
          <BottomSheet open title="Touch" onClose={() => {}}>
            <p>content</p>
          </BottomSheet>
        );
        const backdrop = screen.getByTestId('bottom-sheet-backdrop');
        const onBackdrop = new Event('touchmove', { bubbles: true, cancelable: true });
        backdrop.dispatchEvent(onBackdrop);
        expect(onBackdrop.defaultPrevented).toBe(true);

        const inside = new Event('touchmove', { bubbles: true, cancelable: true });
        screen.getByText('content').dispatchEvent(inside);
        expect(inside.defaultPrevented).toBe(false);
      });
    });
  });

  // On the iPad a tap on Save does not take focus off the field being typed in, so the field is
  // still focused - and the keyboard still up - when the sheet goes. Removing a focused field
  // leaves iOS to tear the keyboard down on its own, which can leave the viewport shifted under
  // the sheet that comes back; blurring it first closes the keyboard the normal way.
  describe('Focus on the way out', () => {
    function Editing({ open }: { open: boolean }) {
      return (
        <BottomSheet open={open} title="Edit" onClose={() => {}}>
          <input aria-label="Finnish name" />
        </BottomSheet>
      );
    }

    function watchBlur(field: HTMLElement) {
      const blurred: boolean[] = [];
      field.addEventListener('focusout', () => blurred.push(field.isConnected));
      return blurred;
    }

    it('blurs a focused field before the sheet is removed', () => {
      const { unmount } = render(<Editing open />);
      const field = screen.getByLabelText('Finnish name');
      field.focus();
      const blurred = watchBlur(field);

      unmount();

      expect(blurred).toEqual([true]);
    });

    it('blurs a focused field before the sheet closes', () => {
      const { rerender } = render(<Editing open />);
      const field = screen.getByLabelText('Finnish name');
      field.focus();
      const blurred = watchBlur(field);

      rerender(<Editing open={false} />);

      expect(blurred).toEqual([true]);
    });
  });
});
