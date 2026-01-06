import React from 'react';

export interface SkeletonProps {
  variant?: 'text' | 'circular' | 'rectangular';
  width?: string | number;
  height?: string | number;
  className?: string;
}

const Skeleton: React.FC<SkeletonProps> = ({
  variant = 'text',
  width,
  height,
  className = '',
}) => {
  // Base styles with clean animation
  const baseStyles = `
    bg-ui-bg-tertiary dark:bg-ui-dark-bg-tertiary
    animate-pulse
    transition-colors duration-ui
  `;

  // Variant styles
  const variantStyles = {
    text: 'rounded h-4',
    circular: 'rounded-full',
    rectangular: 'rounded-ui',
  };

  // Default dimensions
  const defaultWidth = variant === 'circular' ? '40px' : '100%';
  const defaultHeight = variant === 'circular' ? '40px' : variant === 'text' ? '1rem' : '200px';

  const widthStyle = width
    ? typeof width === 'number'
      ? `${width}px`
      : width
    : defaultWidth;

  const heightStyle = height
    ? typeof height === 'number'
      ? `${height}px`
      : height
    : defaultHeight;

  const combinedClassName = `
    ${baseStyles}
    ${variantStyles[variant]}
    ${className}
  `.trim().replace(/\s+/g, ' ');

  return (
    <div
      className={combinedClassName}
      style={{
        width: widthStyle,
        height: heightStyle,
      }}
      aria-hidden="true"
    />
  );
};

// Specialized skeleton for inventory item cards
export const SkeletonInventoryItem: React.FC<{ className?: string }> = ({
  className = '',
}) => (
  <div
    className={`
      bg-white dark:bg-ui-dark-bg
      border border-ui-border dark:border-ui-dark-border
      rounded-ui p-4
      ${className}
    `.trim().replace(/\s+/g, ' ')}
  >
    <div className="flex items-center gap-4">
      {/* Product image */}
      <Skeleton variant="circular" width={56} height={56} />

      {/* Product info */}
      <div className="flex-1 space-y-2">
        <Skeleton variant="text" width="60%" />
        <Skeleton variant="text" width="40%" />
      </div>

      {/* Quantity bar */}
      <div className="w-32">
        <Skeleton variant="rectangular" height={24} />
      </div>

      {/* Expiry badge */}
      <Skeleton variant="rectangular" width={60} height={28} />

      {/* Action buttons */}
      <div className="flex gap-2">
        <Skeleton variant="rectangular" width={44} height={44} />
        <Skeleton variant="rectangular" width={44} height={44} />
      </div>
    </div>
  </div>
);

// Skeleton for card loading
export const SkeletonCard: React.FC<{
  lines?: number;
  className?: string;
}> = ({ lines = 3, className = '' }) => (
  <div
    className={`
      bg-white dark:bg-ui-dark-bg
      border border-ui-border dark:border-ui-dark-border
      rounded-ui p-4
      space-y-3
      ${className}
    `.trim().replace(/\s+/g, ' ')}
  >
    <Skeleton variant="text" width="80%" />
    {Array.from({ length: lines - 1 }).map((_, i) => (
      <Skeleton key={i} variant="text" width={i === lines - 2 ? '60%' : '100%'} />
    ))}
  </div>
);

export default Skeleton;
