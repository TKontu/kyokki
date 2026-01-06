import React from 'react';
import { render, screen } from '@testing-library/react';
import Card, { CardHeader, CardTitle, CardContent, CardFooter } from '../Card';

describe('Card', () => {
  describe('Rendering', () => {
    it('renders children', () => {
      render(<Card>Card content</Card>);
      expect(screen.getByText('Card content')).toBeInTheDocument();
    });

    it('renders as div by default', () => {
      const { container } = render(<Card>Content</Card>);
      expect(container.querySelector('div')).toBeInTheDocument();
    });

    it('renders as button when onClick is provided', () => {
      render(<Card onClick={() => {}}>Clickable</Card>);
      expect(screen.getByRole('button')).toBeInTheDocument();
    });
  });

  describe('Styling', () => {
    it('applies base styles', () => {
      const { container } = render(<Card>Content</Card>);
      const card = container.firstChild as HTMLElement;
      expect(card.className).toContain('bg-white');
      expect(card.className).toContain('dark:bg-ui-dark-bg');
      expect(card.className).toContain('border');
      expect(card.className).toContain('rounded-ui');
    });

    it('applies padding variations', () => {
      const { container: noneContainer } = render(<Card padding="none">None</Card>);
      const { container: smContainer } = render(<Card padding="sm">Small</Card>);
      const { container: mdContainer } = render(<Card padding="md">Medium</Card>);
      const { container: lgContainer } = render(<Card padding="lg">Large</Card>);

      expect((noneContainer.firstChild as HTMLElement).className).not.toContain('p-');
      expect((smContainer.firstChild as HTMLElement).className).toContain('p-3');
      expect((mdContainer.firstChild as HTMLElement).className).toContain('p-4');
      expect((lgContainer.firstChild as HTMLElement).className).toContain('p-6');
    });

    it('applies hoverable styles', () => {
      const { container } = render(<Card hoverable>Hover me</Card>);
      const card = container.firstChild as HTMLElement;
      expect(card.className).toContain('cursor-pointer');
      expect(card.className).toContain('hover:shadow-ui');
    });

    it('accepts custom className', () => {
      const { container } = render(<Card className="custom">Content</Card>);
      expect((container.firstChild as HTMLElement).className).toContain('custom');
    });
  });

  describe('Interactions', () => {
    it('calls onClick when clicked', () => {
      const handleClick = jest.fn();
      render(<Card onClick={handleClick}>Click me</Card>);
      screen.getByRole('button').click();
      expect(handleClick).toHaveBeenCalledTimes(1);
    });
  });
});

describe('Card Subcomponents', () => {
  describe('CardHeader', () => {
    it('renders with border bottom', () => {
      const { container } = render(<CardHeader>Header</CardHeader>);
      const header = container.firstChild as HTMLElement;
      expect(header.className).toContain('border-b');
      expect(screen.getByText('Header')).toBeInTheDocument();
    });
  });

  describe('CardTitle', () => {
    it('renders as h3 with semibold', () => {
      render(<CardTitle>Title</CardTitle>);
      const title = screen.getByText('Title');
      expect(title.tagName).toBe('H3');
      expect(title.className).toContain('font-semibold');
    });
  });

  describe('CardContent', () => {
    it('renders with secondary text color', () => {
      const { container } = render(<CardContent>Content</CardContent>);
      const content = container.firstChild as HTMLElement;
      expect(content.className).toContain('text-ui-text-secondary');
    });
  });

  describe('CardFooter', () => {
    it('renders with border top', () => {
      const { container } = render(<CardFooter>Footer</CardFooter>);
      const footer = container.firstChild as HTMLElement;
      expect(footer.className).toContain('border-t');
      expect(footer.className).toContain('flex');
    });
  });

  describe('Composition', () => {
    it('renders complete card with all subcomponents', () => {
      render(
        <Card>
          <CardHeader>
            <CardTitle>Product Card</CardTitle>
          </CardHeader>
          <CardContent>This is the content</CardContent>
          <CardFooter>Footer content</CardFooter>
        </Card>
      );

      expect(screen.getByText('Product Card')).toBeInTheDocument();
      expect(screen.getByText('This is the content')).toBeInTheDocument();
      expect(screen.getByText('Footer content')).toBeInTheDocument();
    });
  });
});
