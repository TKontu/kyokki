'use client';

import { createContext, useContext } from 'react';

export type ToastType = 'success' | 'error';

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastOptions {
  /** Milliseconds before auto-dismiss. Defaults: success 3000, error 5000. */
  duration?: number;
  /** Optional inline action, e.g. "Undo". Clicking it also dismisses the toast. */
  action?: ToastAction;
}

export interface ToastApi {
  success: (message: string, options?: ToastOptions) => number;
  error: (message: string, options?: ToastOptions) => number;
  dismiss: (id: number) => void;
}

export const ToastContext = createContext<ToastApi | null>(null);

/** Show success and error toasts. Requires `ToastProvider` (mounted in app/providers.tsx). */
export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) {
    throw new Error('useToast must be used inside <ToastProvider>');
  }
  return api;
}

export default useToast;
