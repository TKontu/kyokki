import Link from "next/link";
import Button from "@/components/ui/Button";
import Card, { CardHeader, CardTitle, CardContent } from "@/components/ui/Card";

export default function Home() {
  return (
    <div className="min-h-screen bg-ui-bg dark:bg-ui-dark-bg flex items-center justify-center p-8">
      <Card className="max-w-2xl w-full" padding="lg">
        <CardHeader>
          <CardTitle className="text-3xl">Kyokki - Kitchen Inventory System</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-6">
            <p className="text-lg text-ui-text-secondary dark:text-ui-dark-text-secondary">
              Complete kitchen inventory management - track everything from fresh produce to dry goods,
              seasonings to coffee filters. Receipt scanning with automatic tracking.
            </p>

            <div className="space-y-3">
              <h4 className="font-semibold text-ui-text dark:text-ui-dark-text">Current Status:</h4>
              <ul className="space-y-2 text-ui-text-secondary dark:text-ui-dark-text-secondary">
                <li>✅ Phase 0: Frontend Foundation Complete</li>
                <li>✅ Increment 1.1: Base UI Components Complete</li>
                <li>🔨 Phase 1: Inventory Viewing (In Progress)</li>
              </ul>
            </div>

            <div className="pt-4 flex gap-3">
              <Link href="/components-demo">
                <Button variant="primary" size="lg">
                  View Component Demo
                </Button>
              </Link>
              <Button variant="secondary" size="lg" disabled>
                Inventory (Coming Soon)
              </Button>
            </div>

            <div className="pt-4 text-sm text-ui-text-tertiary dark:text-ui-dark-text-tertiary">
              <p>Built with Next.js 14, TypeScript, and Tailwind CSS</p>
              <p>Clean industrial design optimized for iPad</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
