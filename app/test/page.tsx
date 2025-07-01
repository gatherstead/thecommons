import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function TestPage() {
  return (
    <div className="min-h-screen bg-background text-text p-8 space-y-8">
      <h1 className="text-4xl text-primary">The Commons Style Test</h1>

      <Card>
        <CardContent>
          <div className="flex items-center gap-2 mb-2">
            <h2 className="text-xl font-semibold">Example Business</h2>
            <Badge variant="highlight">Spanish Speaking</Badge>
          </div>
          <p className="text-sm mb-4 text-subtle">
            A charming local shop offering handmade crafts and great coffee.
          </p>
          <div className="flex gap-2">
            <Badge variant="success">Accessible</Badge>
            <Badge variant="subtle">Merchants Assoc.</Badge>
          </div>
          <Button className="mt-4">Visit</Button>
        </CardContent>
      </Card>
    </div>
  );
}
  