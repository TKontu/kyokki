import React from 'react';
import { render, screen } from '@testing-library/react';
import Badge, { ExpiryBadge, StatusBadge } from '../Badge';

describe('Badge', () => {
  describe('Rendering', () => {
    it('renders children', () => {
      render(<Badge>Badge text</Badge>);
      expect(screen.getByText('Badge text')).toBeInTheDocument();
    });
  });

  describe('Variants', () => {
    it('renders default variant', () => {
      const { container } = render(<Badge variant="default">Default</Badge>);
      const badge = container.firstChild as HTMLElement;
      expect(badge.className).toContain('bg-ui-bg-secondary');
    });

    it('renders success variant', () => {
      const { container } = render(<Badge variant="success">Success</Badge>);
      const badge = container.firstChild as HTMLElement;
      expect(badge.className).toContain('bg-green-50');
    });

    it('renders error variant', () => {
      const { container } = render(<Badge variant="error">Error</Badge>);
      const badge = container.firstChild as HTMLElement;
      expect(badge.className).toContain('bg-red-50');
    });

    it('renders warning variant', () => {
      const { container } = render(<Badge variant="warning">Warning</Badge>);
      const badge = container.firstChild as HTMLElement;
      expect(badge.className).toContain('bg-yellow-50');
    });

    it('renders info variant', () => {
      const { container } = render(<Badge variant="info">Info</Badge>);
      const badge = container.firstChild as HTMLElement;
      expect(badge.className).toContain('bg-blue-50');
    });
  });

  describe('Sizes', () => {
    it('renders small size', () => {
      const { container } = render(<Badge size="sm">Small</Badge>);
      const badge = container.firstChild as HTMLElement;
      expect(badge.className).toContain('text-xs');
    });

    it('renders medium size', () => {
      const { container } = render(<Badge size="md">Medium</Badge>);
      const badge = container.firstChild as HTMLElement;
      expect(badge.className).toContain('text-sm');
    });

    it('renders large size', () => {
      const { container } = render(<Badge size="lg">Large</Badge>);
      const badge = container.firstChild as HTMLElement;
      expect(badge.className).toContain('text-base');
    });
  });

  describe('Custom props', () => {
    it('accepts custom className', () => {
      const { container } = render(<Badge className="custom">Badge</Badge>);
      expect((container.firstChild as HTMLElement).className).toContain('custom');
    });
  });
});

describe('ExpiryBadge', () => {
  it('shows "Expired" for negative days', () => {
    render(<ExpiryBadge daysUntilExpiry={-1} />);
    expect(screen.getByText('Expired')).toBeInTheDocument();
  });

  it('shows "Today" for 0 days', () => {
    render(<ExpiryBadge daysUntilExpiry={0} />);
    expect(screen.getByText('Today')).toBeInTheDocument();
  });

  it('shows days for 1-2 days (urgent orange)', () => {
    const { container } = render(<ExpiryBadge daysUntilExpiry={1} />);
    expect(screen.getByText('1d')).toBeInTheDocument();
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toContain('expiry-urgent');
  });

  it('shows days for 3-5 days (warning yellow)', () => {
    const { container } = render(<ExpiryBadge daysUntilExpiry={4} />);
    expect(screen.getByText('4d')).toBeInTheDocument();
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toContain('expiry-warning');
  });

  it('shows days for >5 days (ok green)', () => {
    const { container } = render(<ExpiryBadge daysUntilExpiry={7} />);
    expect(screen.getByText('7d')).toBeInTheDocument();
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toContain('expiry-ok');
  });

  it('shows "10d+" for more than 10 days', () => {
    render(<ExpiryBadge daysUntilExpiry={15} />);
    expect(screen.getByText('10d+')).toBeInTheDocument();
  });
});

describe('StatusBadge', () => {
  it('renders sealed status as success', () => {
    render(<StatusBadge status="sealed" />);
    expect(screen.getByText('Sealed')).toBeInTheDocument();
  });

  it('renders opened status as info', () => {
    render(<StatusBadge status="opened" />);
    expect(screen.getByText('Opened')).toBeInTheDocument();
  });

  it('renders partial status as warning', () => {
    render(<StatusBadge status="partial" />);
    expect(screen.getByText('Partial')).toBeInTheDocument();
  });

  it('renders empty status as default', () => {
    render(<StatusBadge status="empty" />);
    expect(screen.getByText('Empty')).toBeInTheDocument();
  });

  it('renders discarded status as error', () => {
    render(<StatusBadge status="discarded" />);
    expect(screen.getByText('Discarded')).toBeInTheDocument();
  });
});
