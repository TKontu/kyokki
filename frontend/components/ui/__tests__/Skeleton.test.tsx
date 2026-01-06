import React from 'react';
import { render } from '@testing-library/react';
import Skeleton, { SkeletonInventoryItem, SkeletonCard } from '../Skeleton';

describe('Skeleton', () => {
  describe('Rendering', () => {
    it('renders with default props', () => {
      const { container } = render(<Skeleton />);
      const skeleton = container.firstChild as HTMLElement;
      expect(skeleton).toBeInTheDocument();
      expect(skeleton.className).toContain('animate-pulse');
    });

    it('has aria-hidden attribute', () => {
      const { container } = render(<Skeleton />);
      const skeleton = container.firstChild as HTMLElement;
      expect(skeleton.getAttribute('aria-hidden')).toBe('true');
    });
  });

  describe('Variants', () => {
    it('renders text variant with correct styles', () => {
      const { container } = render(<Skeleton variant="text" />);
      const skeleton = container.firstChild as HTMLElement;
      expect(skeleton.className).toContain('rounded');
      expect(skeleton.className).toContain('h-4');
    });

    it('renders circular variant', () => {
      const { container } = render(<Skeleton variant="circular" />);
      const skeleton = container.firstChild as HTMLElement;
      expect(skeleton.className).toContain('rounded-full');
    });

    it('renders rectangular variant', () => {
      const { container } = render(<Skeleton variant="rectangular" />);
      const skeleton = container.firstChild as HTMLElement;
      expect(skeleton.className).toContain('rounded-ui');
    });
  });

  describe('Dimensions', () => {
    it('applies custom width as number', () => {
      const { container } = render(<Skeleton width={200} />);
      const skeleton = container.firstChild as HTMLElement;
      expect(skeleton.style.width).toBe('200px');
    });

    it('applies custom width as string', () => {
      const { container } = render(<Skeleton width="50%" />);
      const skeleton = container.firstChild as HTMLElement;
      expect(skeleton.style.width).toBe('50%');
    });

    it('applies custom height as number', () => {
      const { container } = render(<Skeleton height={100} />);
      const skeleton = container.firstChild as HTMLElement;
      expect(skeleton.style.height).toBe('100px');
    });

    it('applies custom height as string', () => {
      const { container } = render(<Skeleton height="2rem" />);
      const skeleton = container.firstChild as HTMLElement;
      expect(skeleton.style.height).toBe('2rem');
    });

    it('uses default dimensions for circular variant', () => {
      const { container } = render(<Skeleton variant="circular" />);
      const skeleton = container.firstChild as HTMLElement;
      expect(skeleton.style.width).toBe('40px');
      expect(skeleton.style.height).toBe('40px');
    });
  });

  describe('Styling', () => {
    it('has background color with dark mode support', () => {
      const { container } = render(<Skeleton />);
      const skeleton = container.firstChild as HTMLElement;
      expect(skeleton.className).toContain('bg-ui-bg-tertiary');
      expect(skeleton.className).toContain('dark:bg-ui-dark-bg-tertiary');
    });

    it('accepts custom className', () => {
      const { container } = render(<Skeleton className="custom-class" />);
      const skeleton = container.firstChild as HTMLElement;
      expect(skeleton.className).toContain('custom-class');
    });
  });
});

describe('SkeletonInventoryItem', () => {
  it('renders complete skeleton structure', () => {
    const { container } = render(<SkeletonInventoryItem />);
    const skeletons = container.querySelectorAll('[aria-hidden="true"]');

    // Should have multiple skeleton elements (image, name, brand, quantity, expiry, actions)
    expect(skeletons.length).toBeGreaterThan(3);
  });

  it('renders with card wrapper', () => {
    const { container } = render(<SkeletonInventoryItem />);
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain('bg-white');
    expect(wrapper.className).toContain('border');
    expect(wrapper.className).toContain('rounded-ui');
  });

  it('accepts custom className', () => {
    const { container } = render(<SkeletonInventoryItem className="custom" />);
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain('custom');
  });
});

describe('SkeletonCard', () => {
  it('renders with default 3 lines', () => {
    const { container } = render(<SkeletonCard />);
    const skeletons = container.querySelectorAll('[aria-hidden="true"]');
    expect(skeletons.length).toBe(3);
  });

  it('renders custom number of lines', () => {
    const { container } = render(<SkeletonCard lines={5} />);
    const skeletons = container.querySelectorAll('[aria-hidden="true"]');
    expect(skeletons.length).toBe(5);
  });

  it('renders with card wrapper', () => {
    const { container } = render(<SkeletonCard />);
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain('bg-white');
    expect(wrapper.className).toContain('border');
  });

  it('accepts custom className', () => {
    const { container } = render(<SkeletonCard className="custom" />);
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain('custom');
  });
});
