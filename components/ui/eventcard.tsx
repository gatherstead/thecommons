'use client';

import { Card, CardContent } from '@/components/ui/card';

export function EventCard({
  event,
  onClick,
}: {
  event: any;
  onClick?: () => void;
}) {
  const date = new Date(event.start_time);
  const isWeekend = [0, 6].includes(date.getDay());

  function truncate(text: string, maxLength = 120): string {
    return text?.length > maxLength ? text.slice(0, maxLength) + '…' : text;
  }

  function formatDayAndDate(d: Date): string {
    return `${d.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    })}`;
  }

  function formatTime(d: Date): string {
    return d.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });
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
      <Card className="hover:shadow-lg transition-all h-full flex flex-col">
        <CardContent className="space-y-3 p-4 flex flex-col h-full">
          <div className="flex justify-between items-start">
            <span className="text-sm font-semibold text-accent uppercase">
              {formatDayAndDate(date)}
            </span>
            {isWeekend && (
              <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded-full">
                🌞 Weekend
              </span>
            )}
          </div>

          <h3 className="text-lg font-semibold text-primary leading-tight">
            {event.title}
          </h3>

          <div className="text-sm text-muted space-y-1">
            <p>
              <strong className="text-foreground">🕒</strong>{' '}
              {formatTime(date)}
            </p>
            {event.location && (
              <p>
                <strong className="text-foreground">📍</strong>{' '}
                {event.location}
              </p>
            )}
          </div>

          {event.facebook_post && (
            <p className="text-sm text-foreground">{truncate(event.facebook_post)}</p>
          )}

          {tagPills.length > 0 && (
            <div className="flex flex-wrap gap-1">{tagPills}</div>
          )}

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
