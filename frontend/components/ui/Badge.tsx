import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'error' | 'warning' | 'info';
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'default',
  size = 'md',
  className = '',
}) => {
  // Base styles - clean and minimal
  const baseStyles = `
    inline-flex items-center justify-center
    font-medium rounded-ui-sm
    border transition-colors duration-ui
    no-select
  `;

  // Size styles
  const sizeStyles = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-1 text-sm',
    lg: 'px-3 py-1.5 text-base',
  };

  // Variant styles - clean industrial palette
  const variantStyles = {
    default: `
      bg-ui-bg-secondary dark:bg-ui-dark-bg-secondary
      border-ui-border dark:border-ui-dark-border
      text-ui-text-secondary dark:text-ui-dark-text-secondary
    `,
    success: `
      bg-green-50 dark:bg-green-900/20
      border-green-200 dark:border-green-800
      text-green-700 dark:text-green-400
    `,
    error: `
      bg-red-50 dark:bg-red-900/20
      border-red-200 dark:border-red-800
      text-red-700 dark:text-red-400
    `,
    warning: `
      bg-yellow-50 dark:bg-yellow-900/20
      border-yellow-200 dark:border-yellow-800
      text-yellow-700 dark:text-yellow-400
    `,
    info: `
      bg-blue-50 dark:bg-blue-900/20
      border-blue-200 dark:border-blue-800
      text-blue-700 dark:text-blue-400
    `,
  };

  const combinedClassName = `
    ${baseStyles}
    ${sizeStyles[size]}
    ${variantStyles[variant]}
    ${className}
  `.trim().replace(/\s+/g, ' ');

  return <span className={combinedClassName}>{children}</span>;
};

// Specialized badge for expiry status with color coding
export const ExpiryBadge: React.FC<{
  daysUntilExpiry: number;
  className?: string;
}> = ({ daysUntilExpiry, className = '' }) => {
  // Determine color based on days
  let colorClass = '';
  let text = '';

  if (daysUntilExpiry < 0) {
    colorClass = 'bg-expiry-expired/10 border-expiry-expired/30 text-expiry-expired dark:bg-expiry-expired/20';
    text = 'Expired';
  } else if (daysUntilExpiry === 0) {
    colorClass = 'bg-expiry-expired/10 border-expiry-expired/30 text-expiry-expired dark:bg-expiry-expired/20';
    text = 'Today';
  } else if (daysUntilExpiry <= 2) {
    colorClass = 'bg-expiry-urgent/10 border-expiry-urgent/30 text-expiry-urgent dark:bg-expiry-urgent/20';
    text = `${daysUntilExpiry}d`;
  } else if (daysUntilExpiry <= 5) {
    colorClass = 'bg-expiry-warning/10 border-expiry-warning/30 text-expiry-warning dark:bg-expiry-warning/20';
    text = `${daysUntilExpiry}d`;
  } else {
    colorClass = 'bg-expiry-ok/10 border-expiry-ok/30 text-expiry-ok dark:bg-expiry-ok/20';
    text = daysUntilExpiry > 10 ? '10d+' : `${daysUntilExpiry}d`;
  }

  const combinedClassName = `
    inline-flex items-center justify-center
    px-2.5 py-1 text-sm font-medium
    rounded-ui-sm border
    no-select transition-colors duration-ui
    ${colorClass}
    ${className}
  `.trim().replace(/\s+/g, ' ');

  return <span className={combinedClassName}>{text}</span>;
};

// Status badge for inventory items
export const StatusBadge: React.FC<{
  status: 'sealed' | 'opened' | 'partial' | 'empty' | 'discarded';
  className?: string;
}> = ({ status, className = '' }) => {
  const statusConfig = {
    sealed: { label: 'Sealed', variant: 'success' as const },
    opened: { label: 'Opened', variant: 'info' as const },
    partial: { label: 'Partial', variant: 'warning' as const },
    empty: { label: 'Empty', variant: 'default' as const },
    discarded: { label: 'Discarded', variant: 'error' as const },
  };

  const config = statusConfig[status];

  return (
    <Badge variant={config.variant} className={className}>
      {config.label}
    </Badge>
  );
};

export default Badge;
