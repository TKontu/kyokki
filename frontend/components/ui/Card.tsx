import React from 'react';

export interface CardProps {
  children: React.ReactNode;
  className?: string;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  hoverable?: boolean;
  onClick?: () => void;
}

const Card: React.FC<CardProps> = ({
  children,
  className = '',
  padding = 'md',
  hoverable = false,
  onClick,
}) => {
  // Base styles - clean industrial look
  const baseStyles = `
    bg-white dark:bg-ui-dark-bg
    border border-ui-border dark:border-ui-dark-border
    rounded-ui
    shadow-ui-sm dark:shadow-ui-dark-sm
    transition-all duration-ui
  `;

  // Padding options
  const paddingStyles = {
    none: '',
    sm: 'p-3',
    md: 'p-4',
    lg: 'p-6',
  };

  // Hoverable styles
  const hoverStyles = hoverable
    ? `
      cursor-pointer
      hover:shadow-ui dark:hover:shadow-ui-dark
      hover:border-ui-border-strong dark:hover:border-ui-dark-border-strong
      active:scale-[0.99]
    `
    : '';

  const combinedClassName = `
    ${baseStyles}
    ${paddingStyles[padding]}
    ${hoverStyles}
    ${className}
  `.trim().replace(/\s+/g, ' ');

  const Component = onClick ? 'button' : 'div';

  return (
    <Component
      className={combinedClassName}
      onClick={onClick}
      {...(onClick && { type: 'button' })}
    >
      {children}
    </Component>
  );
};

// Card subcomponents for better composition
export const CardHeader: React.FC<{
  children: React.ReactNode;
  className?: string;
}> = ({ children, className = '' }) => (
  <div
    className={`
      border-b border-ui-border dark:border-ui-dark-border
      pb-3 mb-3
      ${className}
    `.trim().replace(/\s+/g, ' ')}
  >
    {children}
  </div>
);

export const CardTitle: React.FC<{
  children: React.ReactNode;
  className?: string;
}> = ({ children, className = '' }) => (
  <h3
    className={`
      text-lg font-semibold
      text-ui-text dark:text-ui-dark-text
      ${className}
    `.trim().replace(/\s+/g, ' ')}
  >
    {children}
  </h3>
);

export const CardContent: React.FC<{
  children: React.ReactNode;
  className?: string;
}> = ({ children, className = '' }) => (
  <div
    className={`
      text-ui-text-secondary dark:text-ui-dark-text-secondary
      ${className}
    `.trim().replace(/\s+/g, ' ')}
  >
    {children}
  </div>
);

export const CardFooter: React.FC<{
  children: React.ReactNode;
  className?: string;
}> = ({ children, className = '' }) => (
  <div
    className={`
      border-t border-ui-border dark:border-ui-dark-border
      pt-3 mt-3
      flex items-center gap-2
      ${className}
    `.trim().replace(/\s+/g, ' ')}
  >
    {children}
  </div>
);

export default Card;
