import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg' | 'xl';
  fullWidth?: boolean;
  loading?: boolean;
  icon?: React.ReactNode;
  children: React.ReactNode;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      fullWidth = false,
      loading = false,
      disabled = false,
      icon,
      children,
      className = '',
      ...props
    },
    ref
  ) => {
    // Base styles - clean and minimal
    const baseStyles = `
      inline-flex items-center justify-center gap-2
      font-medium transition-all duration-ui
      rounded-ui border
      focus:outline-none focus:ring-2 focus:ring-offset-2
      disabled:opacity-50 disabled:cursor-not-allowed
      no-select
    `;

    // Size styles with touch targets
    const sizeStyles = {
      sm: 'min-h-[36px] px-3 text-sm',
      md: 'min-h-touch px-4 text-base',
      lg: 'min-h-[48px] px-5 text-lg',
      xl: 'min-h-touch-lg px-6 text-xl',
    };

    // Variant styles - clean industrial aesthetic
    const variantStyles = {
      primary: `
        bg-primary-600 border-primary-600 text-white
        hover:bg-primary-700 hover:border-primary-700
        active:bg-primary-800
        focus:ring-primary-500
        dark:bg-primary-500 dark:border-primary-500
        dark:hover:bg-primary-600 dark:hover:border-primary-600
      `,
      secondary: `
        bg-white dark:bg-ui-dark-bg
        border-ui-border dark:border-ui-dark-border
        text-ui-text dark:text-ui-dark-text
        hover:bg-ui-bg-secondary dark:hover:bg-ui-dark-bg-secondary
        active:bg-ui-bg-tertiary dark:active:bg-ui-dark-bg-tertiary
        focus:ring-primary-500
        shadow-ui-xs dark:shadow-ui-dark-xs
      `,
      ghost: `
        bg-transparent border-transparent
        text-ui-text dark:text-ui-dark-text
        hover:bg-ui-bg-secondary dark:hover:bg-ui-dark-bg-secondary
        active:bg-ui-bg-tertiary dark:active:bg-ui-dark-bg-tertiary
        focus:ring-primary-500
      `,
      danger: `
        bg-error border-error text-white
        hover:bg-red-600 hover:border-red-600
        active:bg-red-700
        focus:ring-error
        dark:bg-red-600 dark:border-red-600
        dark:hover:bg-red-700 dark:hover:border-red-700
      `,
    };

    const widthStyles = fullWidth ? 'w-full' : '';

    const combinedClassName = `
      ${baseStyles}
      ${sizeStyles[size]}
      ${variantStyles[variant]}
      ${widthStyles}
      ${className}
    `.trim().replace(/\s+/g, ' ');

    return (
      <button
        ref={ref}
        className={combinedClassName}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? (
          <>
            <LoadingSpinner size={size} />
            <span>{children}</span>
          </>
        ) : (
          <>
            {icon && <span className="flex-shrink-0">{icon}</span>}
            <span>{children}</span>
          </>
        )}
      </button>
    );
  }
);

Button.displayName = 'Button';

// Simple loading spinner
const LoadingSpinner: React.FC<{ size: ButtonProps['size'] }> = ({ size }) => {
  const spinnerSizes = {
    sm: 'w-3 h-3',
    md: 'w-4 h-4',
    lg: 'w-5 h-5',
    xl: 'w-6 h-6',
  };

  return (
    <svg
      className={`animate-spin ${spinnerSizes[size || 'md']}`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
};

export default Button;
