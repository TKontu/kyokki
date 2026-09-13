import { renderHook } from '@testing-library/react';
import { useToast } from '../useToast';

describe('useToast', () => {
  it('throws a readable error outside ToastProvider', () => {
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    expect(() => renderHook(() => useToast())).toThrow(
      'useToast must be used inside <ToastProvider>'
    );

    errorSpy.mockRestore();
  });
});
