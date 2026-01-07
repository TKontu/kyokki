'use client';

import React, { useState } from 'react';
import Button from '@/components/ui/Button';
import Card, { CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/Card';
import Badge, { ExpiryBadge as BasicExpiryBadge, StatusBadge } from '@/components/ui/Badge';
import Skeleton, { SkeletonInventoryItem, SkeletonCard } from '@/components/ui/Skeleton';
import { ExpiryBadge } from '@/components/inventory/ExpiryBadge';

export default function ComponentsDemo() {
  const [darkMode, setDarkMode] = useState(false);

  // Calculate demo dates relative to today
  const today = new Date();
  const formatDate = (daysOffset: number) => {
    const date = new Date(today);
    date.setDate(date.getDate() + daysOffset);
    return date.toISOString().split('T')[0];
  };

  // Toggle dark mode on the html element
  React.useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [darkMode]);

  return (
    <div className="min-h-screen bg-ui-bg dark:bg-ui-dark-bg transition-colors">
      <div className="max-w-7xl mx-auto p-8 space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h1 className="text-4xl font-bold text-ui-text dark:text-ui-dark-text">
            UI Components Demo
          </h1>
          <Button
            variant="secondary"
            onClick={() => setDarkMode(!darkMode)}
          >
            {darkMode ? '☀️ Light' : '🌙 Dark'} Mode
          </Button>
        </div>

        <p className="text-ui-text-secondary dark:text-ui-dark-text-secondary">
          Clean industrial UI components for iPad - optimized for touch with light/dark themes
        </p>

        {/* Buttons */}
        <Card>
          <CardHeader>
            <CardTitle>Buttons</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              <div>
                <h4 className="text-sm font-semibold mb-3 text-ui-text dark:text-ui-dark-text">Variants</h4>
                <div className="flex flex-wrap gap-3">
                  <Button variant="primary">Primary</Button>
                  <Button variant="secondary">Secondary</Button>
                  <Button variant="ghost">Ghost</Button>
                  <Button variant="danger">Danger</Button>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold mb-3 text-ui-text dark:text-ui-dark-text">Sizes (Touch Targets)</h4>
                <div className="flex flex-wrap items-end gap-3">
                  <Button size="sm">Small (36px)</Button>
                  <Button size="md">Medium (44px)</Button>
                  <Button size="lg">Large (48px)</Button>
                  <Button size="xl">Extra Large (56px)</Button>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold mb-3 text-ui-text dark:text-ui-dark-text">States</h4>
                <div className="flex flex-wrap gap-3">
                  <Button disabled>Disabled</Button>
                  <Button loading>Loading</Button>
                  <Button fullWidth>Full Width</Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Badges */}
        <Card>
          <CardHeader>
            <CardTitle>Badges</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              <div>
                <h4 className="text-sm font-semibold mb-3 text-ui-text dark:text-ui-dark-text">Variants</h4>
                <div className="flex flex-wrap gap-3">
                  <Badge variant="default">Default</Badge>
                  <Badge variant="success">Success</Badge>
                  <Badge variant="error">Error</Badge>
                  <Badge variant="warning">Warning</Badge>
                  <Badge variant="info">Info</Badge>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold mb-3 text-ui-text dark:text-ui-dark-text">Expiry Badges (Basic)</h4>
                <div className="flex flex-wrap gap-3">
                  <BasicExpiryBadge daysUntilExpiry={-1} />
                  <BasicExpiryBadge daysUntilExpiry={0} />
                  <BasicExpiryBadge daysUntilExpiry={1} />
                  <BasicExpiryBadge daysUntilExpiry={4} />
                  <BasicExpiryBadge daysUntilExpiry={7} />
                  <BasicExpiryBadge daysUntilExpiry={15} />
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold mb-3 text-ui-text dark:text-ui-dark-text">Status Badges</h4>
                <div className="flex flex-wrap gap-3">
                  <StatusBadge status="sealed" />
                  <StatusBadge status="opened" />
                  <StatusBadge status="partial" />
                  <StatusBadge status="empty" />
                  <StatusBadge status="discarded" />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Enhanced Expiry Badge */}
        <Card>
          <CardHeader>
            <CardTitle>Enhanced Expiry Badge (Increment 1.3)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              <div>
                <h4 className="text-sm font-semibold mb-3 text-ui-text dark:text-ui-dark-text">
                  Expiry Urgency Levels
                </h4>
                <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary mb-3">
                  Color-coded badges with automatic formatting and warning icons
                </p>
                <div className="flex flex-wrap gap-3">
                  <ExpiryBadge expiryDate={formatDate(-5)} />
                  <ExpiryBadge expiryDate={formatDate(0)} />
                  <ExpiryBadge expiryDate={formatDate(1)} />
                  <ExpiryBadge expiryDate={formatDate(2)} />
                  <ExpiryBadge expiryDate={formatDate(5)} />
                  <ExpiryBadge expiryDate={formatDate(7)} />
                  <ExpiryBadge expiryDate={formatDate(14)} />
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold mb-3 text-ui-text dark:text-ui-dark-text">
                  Scanned Dates (with 📅 icon)
                </h4>
                <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary mb-3">
                  Dates from GS1 DataMatrix barcodes show calendar icon for accuracy
                </p>
                <div className="flex flex-wrap gap-3">
                  <ExpiryBadge expiryDate={formatDate(-2)} expirySource="scanned" />
                  <ExpiryBadge expiryDate={formatDate(0)} expirySource="scanned" />
                  <ExpiryBadge expiryDate={formatDate(3)} expirySource="scanned" />
                  <ExpiryBadge expiryDate={formatDate(7)} expirySource="scanned" />
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold mb-3 text-ui-text dark:text-ui-dark-text">
                  Color Coding Legend
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                  <div className="flex items-center gap-2">
                    <ExpiryBadge expiryDate={formatDate(-1)} />
                    <span className="text-ui-text-secondary dark:text-ui-dark-text-secondary">
                      Red: Expired (past dates)
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <ExpiryBadge expiryDate={formatDate(0)} />
                    <span className="text-ui-text-secondary dark:text-ui-dark-text-secondary">
                      Orange: Today/Tomorrow
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <ExpiryBadge expiryDate={formatDate(2)} />
                    <span className="text-ui-text-secondary dark:text-ui-dark-text-secondary">
                      Yellow: Soon (2-3 days)
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <ExpiryBadge expiryDate={formatDate(5)} />
                    <span className="text-ui-text-secondary dark:text-ui-dark-text-secondary">
                      Green: Fresh (4+ days)
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Cards */}
        <Card>
          <CardHeader>
            <CardTitle>Cards</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card padding="md">
                <CardTitle>Basic Card</CardTitle>
                <p className="mt-2 text-ui-text-secondary dark:text-ui-dark-text-secondary">
                  This is a basic card with medium padding
                </p>
              </Card>

              <Card padding="lg" hoverable>
                <CardHeader>
                  <CardTitle>Hoverable Card</CardTitle>
                </CardHeader>
                <CardContent>
                  Hover over this card to see the effect
                </CardContent>
                <CardFooter>
                  <Button size="sm">Action</Button>
                </CardFooter>
              </Card>
            </div>
          </CardContent>
        </Card>

        {/* Skeletons */}
        <Card>
          <CardHeader>
            <CardTitle>Loading Skeletons</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              <div>
                <h4 className="text-sm font-semibold mb-3 text-ui-text dark:text-ui-dark-text">Basic Skeletons</h4>
                <div className="space-y-2">
                  <Skeleton variant="text" />
                  <Skeleton variant="text" width="80%" />
                  <Skeleton variant="text" width="60%" />
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold mb-3 text-ui-text dark:text-ui-dark-text">Skeleton Card</h4>
                <SkeletonCard lines={4} />
              </div>

              <div>
                <h4 className="text-sm font-semibold mb-3 text-ui-text dark:text-ui-dark-text">Skeleton Inventory Item</h4>
                <SkeletonInventoryItem />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Theme Info */}
        <Card>
          <CardHeader>
            <CardTitle>Theme System</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-ui-text-secondary dark:text-ui-dark-text-secondary">
              All components support both light and dark themes. Toggle the theme using the button at the top.
              The design follows a clean industrial aesthetic similar to iPad and OpenWebUI.
            </p>
            <div className="mt-4 space-y-2 text-sm">
              <p className="text-ui-text dark:text-ui-dark-text">
                <strong>Touch Targets:</strong> All interactive elements meet Apple&apos;s HIG minimum of 44px
              </p>
              <p className="text-ui-text dark:text-ui-dark-text">
                <strong>Colors:</strong> Subtle, professional palette with good contrast
              </p>
              <p className="text-ui-text dark:text-ui-dark-text">
                <strong>Shadows:</strong> Minimal and clean, stronger in dark mode
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
