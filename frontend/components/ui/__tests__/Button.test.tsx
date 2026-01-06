import React from 'react';
import { render, screen } from '@testing-library/react';
import Button from '../Button';

describe('Button', () => {
  describe('Rendering', () => {
    it('renders with children', () => {
      render(<Button>Click me</Button>);
      expect(screen.getByRole('button', { name: 'Click me' })).toBeInTheDocument();
    });

    it('renders with icon', () => {
      render(
        <Button icon={<span data-testid="icon">Icon</span>}>
          With Icon
        </Button>
      );
      expect(screen.getByTestId('icon')).toBeInTheDocument();
      expect(screen.getByText('With Icon')).toBeInTheDocument();
    });
  });

  describe('Variants', () => {
    it('renders primary variant', () => {
      render(<Button variant="primary">Primary</Button>);
      const button = screen.getByRole('button');
      expect(button.className).toContain('bg-primary-600');
    });

    it('renders secondary variant', () => {
      render(<Button variant="secondary">Secondary</Button>);
      const button = screen.getByRole('button');
      expect(button.className).toContain('bg-white');
    });

    it('renders ghost variant', () => {
      render(<Button variant="ghost">Ghost</Button>);
      const button = screen.getByRole('button');
      expect(button.className).toContain('bg-transparent');
    });

    it('renders danger variant', () => {
      render(<Button variant="danger">Danger</Button>);
      const button = screen.getByRole('button');
      expect(button.className).toContain('bg-error');
    });
  });

  describe('Sizes and Touch Targets', () => {
    it('renders sm size with correct height', () => {
      render(<Button size="sm">Small</Button>);
      const button = screen.getByRole('button');
      expect(button.className).toContain('min-h-[36px]');
    });

    it('renders md size with 44px touch target', () => {
      render(<Button size="md">Medium</Button>);
      const button = screen.getByRole('button');
      expect(button.className).toContain('min-h-touch');
    });

    it('renders lg size with correct height', () => {
      render(<Button size="lg">Large</Button>);
      const button = screen.getByRole('button');
      expect(button.className).toContain('min-h-[48px]');
    });

    it('renders xl size with 56px touch target', () => {
      render(<Button size="xl">Extra Large</Button>);
      const button = screen.getByRole('button');
      expect(button.className).toContain('min-h-touch-lg');
    });
  });

  describe('States', () => {
    it('handles disabled state', () => {
      render(<Button disabled>Disabled</Button>);
      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
      expect(button.className).toContain('disabled:opacity-50');
    });

    it('handles loading state', () => {
      render(<Button loading>Loading</Button>);
      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
      // Loading spinner should be present
      const svg = button.querySelector('svg');
      expect(svg).toBeInTheDocument();
      expect(svg?.getAttribute('class')).toContain('animate-spin');
    });

    it('renders fullWidth', () => {
      render(<Button fullWidth>Full Width</Button>);
      const button = screen.getByRole('button');
      expect(button.className).toContain('w-full');
    });
  });

  describe('Accessibility', () => {
    it('has proper button role', () => {
      render(<Button>Accessible</Button>);
      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    it('prevents text selection', () => {
      render(<Button>No Select</Button>);
      const button = screen.getByRole('button');
      expect(button.className).toContain('no-select');
    });

    it('has focus ring styles', () => {
      render(<Button>Focus</Button>);
      const button = screen.getByRole('button');
      expect(button.className).toContain('focus:ring-2');
    });
  });

  describe('Custom props', () => {
    it('accepts custom className', () => {
      render(<Button className="custom-class">Custom</Button>);
      const button = screen.getByRole('button');
      expect(button.className).toContain('custom-class');
    });

    it('passes through onClick handler', () => {
      const handleClick = jest.fn();
      render(<Button onClick={handleClick}>Click</Button>);
      screen.getByRole('button').click();
      expect(handleClick).toHaveBeenCalledTimes(1);
    });
  });
});
