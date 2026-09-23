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
  });
});
