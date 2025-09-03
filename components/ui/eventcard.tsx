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

  const summary = event.card_summary || event.facebook_post || event.description;

  const tagPills = (event.tags || []).map((tag: string) => (
    <span
      key={tag}
      className="text-xs font-medium bg-subtle text-text px-2 py-0.5 rounded-full shadow-sm"
    >
      {tag}
    </span>
  ));

  return (
    <div
      onClick={isCompact ? onClick : undefined}
      className={cn(
        isCompact &&
          'cursor-pointer group hover:scale-[1.01] active:scale-[0.99] transition'
      )}
    >
     <Card
  className={cn(
    'transition-all h-full flex flex-col bg-white', // explicitly white
    isCompact && 'hover:shadow-lg'
  )}
>
        <CardContent className="flex flex-col h-full p-4 space-y-3">
          {/* Date & Weekend */}
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

          {/* Title */}
          <h3 className="text-lg font-semibold text-primary leading-tight">
            {event.title}
          </h3>

          {/* Time & Location */}
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

          {/* Tags */}
          {tagPills.length > 0 && (
            <div className="flex flex-wrap gap-1">{tagPills}</div>
          )}

          {/* Description */}
          {summary && (
            <p
              className={cn(
                'text-sm text-foreground whitespace-pre-line',
                isCompact ? 'line-clamp-2' : ''
              )}
            >
              {summary}
            </p>
          )}

          {/* Optional Image (expanded only) */}
          {!isCompact && event.image_url && (
            <img
              src={event.image_url}
              alt={event.title}
              className="rounded-md max-h-48 w-full object-cover"
            />
          )}

          {/* CTAs */}
          <div className="mt-auto flex flex-col gap-1">
            {/* External CTA Link */}
            {event.cta_url && (
              <a
                href={event.cta_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-accent underline text-sm"
              >
                🔗 Link
              </a>
            )}

            {/* Modal Trigger */}
            <p
              className="text-sm text-accent font-medium"
              onClick={onClick}
            >
              View details →
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
