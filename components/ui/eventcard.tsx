'use client';

import { Card, CardContent } from '@/components/ui/card';

export function EventCard({
  event,
  onClick,
}: {
  event: any;
  onClick?: () => void;
}) {
  const isWeekend = [0, 6].includes(new Date(event.start_time).getDay());

  function truncate(text: string, maxLength = 120): string {
    return text?.length > maxLength ? text.slice(0, maxLength) + '…' : text;
  }

  function formatDate(dateStr: string): string {
    const date = new Date(dateStr);
    return `${date.toLocaleDateString('en-US')} ${date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    })}`;
  }

  const tagPills = (event.tags || []).map((tag: string) => (
    <span
      key={tag}
      className="text-xs font-medium bg-subtle text-text px-2 py-0.5 rounded-full shadow-sm"
    >
      {tag}
    </span>
  ));

  return (
    <div onClick={onClick} className="cursor-pointer">
      <Card className="hover:shadow-lg transition-all">
        <CardContent className="space-y-3 p-4">
          <h3 className="text-lg font-semibold text-primary">{event.title}</h3>

          <p className="text-sm text-muted italic">{formatDate(event.start_time)}</p>

          {isWeekend && (
            <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded-full">
              🌞 Weekend Event
            </span>
          )}

          {event.facebook_post && (
            <p className="text-sm text-foreground">{truncate(event.facebook_post)}</p>
          )}

          {tagPills.length > 0 && <div className="flex flex-wrap gap-1">{tagPills}</div>}

          {event.image_url && (
            <img
              src={event.image_url}
              alt={event.title}
              className="rounded-md max-h-48 w-full object-cover"
            />
          )}

          {event.cta_url && (
            <a
              href={event.cta_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              className="inline-block text-accent underline text-sm mt-2"
            >
              Learn more →
            </a>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
