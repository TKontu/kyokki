import React from 'react';
import { act, render, screen, fireEvent } from '@testing-library/react';
import { ToastProvider } from '../Toast';
import { useToast, type ToastOptions } from '@/hooks/useToast';

function Trigger({
  type,
  message,
  options,
}: {
  type: 'success' | 'error';
  message: string;
  options?: ToastOptions;
}) {
  const toast = useToast();
  return <button onClick={() => toast[type](message, options)}>{`show ${message}`}</button>;
}

function show(message: string) {
  fireEvent.click(screen.getByRole('button', { name: `show ${message}` }));
}

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
});

describe('Toast', () => {
  describe('Rendering', () => {
    it('renders a success toast as a polite status', () => {
      render(
        <ToastProvider>
          <Trigger type="success" message="Saved" />
        </ToastProvider>
      );
      show('Saved');

      const toast = screen.getByRole('status');
      expect(toast).toHaveTextContent('Saved');
      expect(toast).toHaveAttribute('aria-live', 'polite');
    });

    it('renders an error toast as an alert', () => {
      render(
        <ToastProvider>
          <Trigger type="error" message="Failed" />
        </ToastProvider>
      );
      show('Failed');

      expect(screen.getByRole('alert')).toHaveTextContent('Failed');
    });

    it('stacks toasts in order and keeps at most three', () => {
      render(
        <ToastProvider>
          <Trigger type="success" message="one" />
          <Trigger type="success" message="two" />
          <Trigger type="success" message="three" />
          <Trigger type="success" message="four" />
        </ToastProvider>
      );
      show('one');
      show('two');
      show('three');
      const firstThree = screen.getAllByRole('status').map((t) => t.textContent ?? '');
      expect(firstThree).toHaveLength(3);
      expect(firstThree[0]).toContain('one');
      expect(firstThree[2]).toContain('three');

      show('four');

      const texts = screen.getAllByRole('status').map((t) => t.textContent ?? '');
      expect(texts).toHaveLength(3);
      expect(texts.some((t) => t.includes('one'))).toBe(false);
      expect(texts[2]).toContain('four');
    });
  });

  describe('Dismissal', () => {
    it('auto-dismisses success toasts after 3 seconds', () => {
      render(
        <ToastProvider>
          <Trigger type="success" message="Saved" />
        </ToastProvider>
      );
      show('Saved');

      act(() => {
        jest.advanceTimersByTime(2999);
      });
      expect(screen.getByRole('status')).toBeInTheDocument();

      act(() => {
        jest.advanceTimersByTime(1);
      });
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });

    it('auto-dismisses error toasts after 5 seconds', () => {
      render(
        <ToastProvider>
          <Trigger type="error" message="Failed" />
        </ToastProvider>
      );
      show('Failed');

      act(() => {
        jest.advanceTimersByTime(4999);
      });
      expect(screen.getByRole('alert')).toBeInTheDocument();

      act(() => {
        jest.advanceTimersByTime(1);
      });
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('honours a custom duration', () => {
      render(
        <ToastProvider>
          <Trigger type="success" message="Quick" options={{ duration: 1000 }} />
        </ToastProvider>
      );
      show('Quick');

      act(() => {
        jest.advanceTimersByTime(1000);
      });

      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });

    it('dismisses immediately from a 44pt dismiss button', () => {
      render(
        <ToastProvider>
          <Trigger type="error" message="Failed" />
        </ToastProvider>
      );
      show('Failed');

      const dismiss = screen.getByRole('button', { name: 'Dismiss' });
      expect(dismiss.className).toContain('min-h-touch');
      fireEvent.click(dismiss);

      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('runs the action and dismisses the toast', () => {
      const onClick = jest.fn();
      render(
        <ToastProvider>
          <Trigger
            type="success"
            message="Consumed"
            options={{ action: { label: 'Undo', onClick } }}
          />
        </ToastProvider>
      );
      show('Consumed');

      fireEvent.click(screen.getByRole('button', { name: 'Undo' }));

      expect(onClick).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });

    it('clears pending timers when the provider unmounts', () => {
      const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
      const { unmount } = render(
        <ToastProvider>
          <Trigger type="success" message="Saved" />
        </ToastProvider>
      );
      show('Saved');

      unmount();

      expect(jest.getTimerCount()).toBe(0);
      expect(errorSpy).not.toHaveBeenCalled();
      errorSpy.mockRestore();
    });
  });
});
