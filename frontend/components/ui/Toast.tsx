'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  ToastContext,
  type ToastAction,
  type ToastApi,
  type ToastOptions,
  type ToastType,
} from '@/hooks/useToast';

const MAX_VISIBLE = 3;

const DEFAULT_DURATION: Record<ToastType, number> = {
  success: 3000,
  error: 5000,
};

export interface ToastProps {
  type: ToastType;
  message: string;
  action?: ToastAction;
  onDismiss: () => void;
  className?: string;
}

// Border and text colours from Badge's success/error variants. The surface stays solid
// (Badge's translucent tints would let page content show through a floating toast).
const typeStyles: Record<ToastType, string> = {
  success: `
    border-green-200 dark:border-green-800
    text-green-700 dark:text-green-400
  `,
  error: `
    border-red-200 dark:border-red-800
    text-red-700 dark:text-red-400
  `,
};

const controlStyles = `
  min-h-touch min-w-touch px-3 rounded-ui font-medium no-select
  transition-all duration-ui
  focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500
`;

const Toast: React.FC<ToastProps> = ({ type, message, action, onDismiss, className = '' }) => {
  const roleProps =
    type === 'error'
      ? { role: 'alert' as const }
      : { role: 'status' as const, 'aria-live': 'polite' as const };

  const combinedClassName = `
    pointer-events-auto flex items-center gap-2 w-full
    pl-4 pr-1 py-1 rounded-ui-lg border
    bg-white dark:bg-ui-dark-bg shadow-ui-md dark:shadow-ui-dark-md
    ${typeStyles[type]}
    ${className}
  `
    .trim()
    .replace(/\s+/g, ' ');

  return (
    <div {...roleProps} className={combinedClassName}>
      <p className="flex-1 text-sm">{message}</p>
      {action && (
        <button
          type="button"
          className={`${controlStyles} underline`.trim().replace(/\s+/g, ' ')}
          onClick={() => {
            action.onClick();
            onDismiss();
          }}
        >
          {action.label}
        </button>
      )}
      <button
        type="button"
        aria-label="Dismiss"
        className={controlStyles.trim().replace(/\s+/g, ' ')}
        onClick={onDismiss}
      >
        <span aria-hidden="true">✕</span>
      </button>
    </div>
  );
};

interface ToastEntry {
  id: number;
  type: ToastType;
  message: string;
  action?: ToastAction;
}

export interface ToastProviderProps {
  children: React.ReactNode;
}

/** Holds toast state and renders the stack. Mount once, near the app root. */
export function ToastProvider({ children }: ToastProviderProps) {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const [mounted, setMounted] = useState(false);
  const nextId = useRef(0);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  useEffect(() => {
    setMounted(true);
    const pending = timers.current;
    return () => {
      pending.forEach((timer) => clearTimeout(timer));
      pending.clear();
    };
  }, []);

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const show = useCallback(
    (type: ToastType, message: string, options: ToastOptions = {}) => {
      nextId.current += 1;
      const id = nextId.current;
      setToasts((prev) => [...prev, { id, type, message, action: options.action }].slice(-MAX_VISIBLE));
      timers.current.set(
        id,
        setTimeout(() => dismiss(id), options.duration ?? DEFAULT_DURATION[type])
      );
      return id;
    },
    [dismiss]
  );

  const api = useMemo<ToastApi>(
    () => ({
      success: (message, options) => show('success', message, options),
      error: (message, options) => show('error', message, options),
      dismiss,
    }),
    [show, dismiss]
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      {mounted &&
        toasts.length > 0 &&
        createPortal(
          <div
            className="pointer-events-none fixed inset-x-0 top-0 z-50 flex flex-col items-center gap-2 px-4 pt-[max(1rem,env(safe-area-inset-top))]"
          >
            <div className="flex w-full max-w-md flex-col gap-2">
              {toasts.map((toast) => (
                <Toast
                  key={toast.id}
                  type={toast.type}
                  message={toast.message}
                  action={toast.action}
                  onDismiss={() => dismiss(toast.id)}
                />
              ))}
            </div>
          </div>,
          document.body
        )}
    </ToastContext.Provider>
  );
}

export default Toast;
