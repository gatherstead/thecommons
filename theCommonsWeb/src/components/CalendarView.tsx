import { useState, useMemo } from 'react';
import type { Event } from '../components/EventCard';
import { EventCard } from './EventCard';

interface CalendarViewProps {
    events: Event[];
}

export function CalendarView({ events }: CalendarViewProps) {
    const [currentDate, setCurrentDate] = useState(new Date());
    const [selectedDay, setSelectedDay] = useState<Date | null>(null);

    const currentMonth = currentDate.getMonth();
    const currentYear = currentDate.getFullYear();

    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
    const firstDayOfMonth = new Date(currentYear, currentMonth, 1).getDay();

    const calendarDays = useMemo(() => {
        const days = [];
        // Padding for first day
        for (let i = 0; i < firstDayOfMonth; i++) {
            days.push(null);
        }
        // Days of month
        for (let i = 1; i <= daysInMonth; i++) {
            days.push(new Date(currentYear, currentMonth, i));
        }
        return days;
    }, [currentMonth, currentYear, daysInMonth, firstDayOfMonth]);

    const monthName = currentDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

    const nextMonth = () => {
        setCurrentDate(new Date(currentYear, currentMonth + 1, 1));
    };

    const prevMonth = () => {
        setCurrentDate(new Date(currentYear, currentMonth - 1, 1));
    };

    const selectedDayEvents = useMemo(() => {
        if (!selectedDay) return [];
        return events.filter(e =>
            e.date.getDate() === selectedDay.getDate() &&
            e.date.getMonth() === selectedDay.getMonth() &&
            e.date.getFullYear() === selectedDay.getFullYear()
        );
    }, [selectedDay, events]);

    return (
        <div className="newspaper-border bg-[var(--color-paper)] p-4 md:p-8 relative">
            <div className="flex justify-between items-center mb-8 border-b-4 border-[var(--color-border)] pb-4">
                <button
                    onClick={prevMonth}
                    className="font-bold uppercase tracking-widest text-sm hover:text-[var(--color-accent)] transition-colors cursor-pointer"
                >
                    &larr; Prev
                </button>
                <div className="text-center">
                    <h2 className="font-[var(--font-headline)] text-3xl md:text-4xl font-black uppercase tracking-tighter">
                        {monthName} Gazette
                    </h2>
                    <p className="text-sm italic font-[var(--font-accent)] mt-1">"Every event fit to print"</p>
                </div>
                <button
                    onClick={nextMonth}
                    className="font-bold uppercase tracking-widest text-sm hover:text-[var(--color-accent)] transition-colors cursor-pointer"
                >
                    Next &rarr;
                </button>
            </div>

            <div className="grid grid-cols-7 border-t-2 border-l-2 border-[var(--color-border)]">
                {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
                    <div key={day} className="border-r-2 border-b-2 border-[var(--color-border)] bg-[#ebe7de] p-2 text-center font-bold font-[var(--font-headline)] uppercase text-xs tracking-widest">
                        {day}
                    </div>
                ))}
                {calendarDays.map((day, i) => {
                    if (!day) return <div key={`empty-${i}`} className="border-r-2 border-b-2 border-[var(--color-border)] min-h-[120px] bg-[#f4f1ea]" />;

                    const dayEvents = events.filter(e =>
                        e.date.getDate() === day.getDate() &&
                        e.date.getMonth() === day.getMonth() &&
                        e.date.getFullYear() === day.getFullYear()
                    );

                    return (
                        <div
                            key={day.toISOString()}
                            onClick={() => setSelectedDay(day)}
                            className="border-r-2 border-b-2 border-[var(--color-border)] min-h-[120px] p-2 transition-colors hover:bg-[#ebe7de] cursor-pointer group"
                        >
                            <div className="font-bold text-sm mb-1 group-hover:text-[var(--color-accent)]">{day.getDate()}</div>
                            <div className="space-y-1">
                                {dayEvents.slice(0, 3).map(event => (
                                    <div key={event.id} className="text-[10px] leading-tight border-b border-[var(--color-border)] pb-1 last:border-0">
                                        <div className="font-bold uppercase truncate">{event.title}</div>
                                        <div className="text-[var(--color-muted)] truncate">{event.time}</div>
                                    </div>
                                ))}
                                {dayEvents.length > 3 && (
                                    <div className="text-[10px] font-bold italic text-[var(--color-muted)] pt-1">
                                        + {dayEvents.length - 3} more...
                                    </div>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>

            {selectedDay && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50 animate-in fade-in duration-200">
                    <div className="bg-[var(--color-paper)] newspaper-border max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6 md:p-10 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
                        <div className="flex justify-between items-start border-b-4 border-[var(--color-border)] pb-4 mb-6">
                            <div>
                                <p className="text-xs uppercase tracking-widest text-[var(--color-muted)] mb-1">
                                    Daily Bulletin — {selectedDay.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                                </p>
                                <h3 className="font-[var(--font-headline)] text-3xl font-black uppercase tracking-tighter">
                                    Events of the Day
                                </h3>
                            </div>
                            <button
                                onClick={() => setSelectedDay(null)}
                                className="text-2xl hover:text-[var(--color-accent)] transition-colors cursor-pointer"
                            >
                                ✕
                            </button>
                        </div>

                        <div className="space-y-8">
                            {selectedDayEvents.length === 0 ? (
                                <div className="text-center py-12 border-2 border-dashed border-[var(--color-border)]">
                                    <p className="italic font-[var(--font-accent)]">No events scheduled for this day.</p>
                                </div>
                            ) : (
                                selectedDayEvents.map(event => (
                                    <div key={event.id} className="relative">
                                        <EventCard event={event} />
                                        <hr className="newspaper-divider-thin mt-6" />
                                    </div>
                                ))
                            )}
                        </div>

                        <div className="mt-10 pt-6 border-t-2 border-[var(--color-border)] text-center">
                            <button
                                onClick={() => setSelectedDay(null)}
                                className="px-8 py-2 border-2 border-[var(--color-ink)] font-bold uppercase tracking-widest hover:bg-[var(--color-ink)] hover:text-[var(--color-paper)] transition-all cursor-pointer"
                            >
                                Return to Calendar
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
