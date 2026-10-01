import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { Providers } from '../providers';
import { useToast } from '@/hooks/useToast';
import { THEME_COLOR_DARK, THEME_COLOR_LIGHT } from '@/lib/brand';
import { THEME_KEY } from '@/lib/theme';

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

  describe('the theme mount effect (round 2026-09-30-1)', () => {
    function addThemeColorMetas() {
      for (const [media, content] of [
        ['(prefers-color-scheme: light)', THEME_COLOR_LIGHT],
        ['(prefers-color-scheme: dark)', THEME_COLOR_DARK],
      ] as const) {
        const meta = document.createElement('meta');
        meta.setAttribute('name', 'theme-color');
        meta.setAttribute('media', media);
        meta.setAttribute('content', content);
        document.head.appendChild(meta);
      }
    }

    beforeEach(() => {
      document.documentElement.classList.remove('light', 'dark');
      document.head.innerHTML = '';
      addThemeColorMetas();
    });

    afterEach(() => {
      window.localStorage.clear();
    });

    it('lands the forced status-bar colour once mounted, as the boot script cannot', () => {
      window.localStorage.setItem(THEME_KEY, 'dark');
      // No class yet: simulates a hydration mismatch (or any other reason) having reverted
      // what the boot script set, which is exactly what this effect exists to repair.

      render(<Providers>{null}</Providers>);

      expect(document.documentElement).toHaveClass('dark');
      const metas = Array.from(document.querySelectorAll('meta[name="theme-color"]'));
      for (const meta of metas) {
        expect(meta).toHaveAttribute('content', THEME_COLOR_DARK);
      }
    });

    it('leaves System alone: no class, each tag its own colour', () => {
      render(<Providers>{null}</Providers>);

      expect(document.documentElement).not.toHaveClass('dark');
      expect(document.documentElement).not.toHaveClass('light');
      const metas = Array.from(document.querySelectorAll('meta[name="theme-color"]'));
      const [light, dark] = metas;
      expect(light).toHaveAttribute('content', THEME_COLOR_LIGHT);
      expect(dark).toHaveAttribute('content', THEME_COLOR_DARK);
    });
  });
});
