'use client';

import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

type EventCardProps = {
  event: any;
  variant?: 'compact' | 'expanded';
  onClick?: () => void;
};

export function EventCard({ event, variant = 'compact', onClick }: EventCardProps) {
  const date = new Date(event.start_time);
  const isWeekend = [0, 6].includes(date.getDay());
  const isCompact = variant === 'compact';

  function formatDayAndDate(d: Date): string {
    return d.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  }

  function formatTime(d: Date): string {
    return d.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  const summary = event.facebook_post || event.description;

  const tagPills = (event.tags || []).map((tag: string) => (
    <span
      key={tag}
      className="text-xs font-medium bg-subtle text-text px-2 py-0.5 rounded-full shadow-sm"
    >
      {tag}
    </span>
  ));

  return (
    <div onClick={isCompact ? onClick : undefined} className={cn(isCompact && 'cursor-pointer')}>
      <Card
        className={cn(
          'transition-all h-full flex flex-col',
          isCompact && 'hover:shadow-lg'
        )}
      >
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
              <strong className="text-foreground">🕒</strong> {formatTime(date)}
            </p>
            {event.location && (
              <p>
                <strong className="text-foreground">📍</strong> {event.location}
              </p>
            )}
          </div>

          {tagPills.length > 0 && <div className="flex flex-wrap gap-1">{tagPills}</div>}

          {summary && (
            <p className={cn('text-sm text-foreground', isCompact && 'line-clamp-2')}>
              {summary}
            </p>
          )}

          {!isCompact && event.image_url && (
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