import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { Providers } from '../providers';
import { useToast } from '@/hooks/useToast';

function ToastButton() {
  const toast = useToast();
  return <button onClick={() => toast.success('Hello from providers')}>notify</button>;
}

describe('Providers', () => {
  it('makes toasts available to the whole app', () => {
    render(
      <Providers>
        <ToastButton />
      </Providers>
    );

    fireEvent.click(screen.getByRole('button', { name: 'notify' }));

    expect(screen.getByRole('status')).toHaveTextContent('Hello from providers');
  });
});
