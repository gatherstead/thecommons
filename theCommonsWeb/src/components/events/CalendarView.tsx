import { useState, useMemo, useEffect } from 'react';
import type { FrontendEvent, TownOption } from '../../models/eventsModels';
import { EventRow } from './EventRow';
import { Modal } from '../ui/Modal';

interface CalendarViewProps {
    events: FrontendEvent[];
    onEventClick?: (event: FrontendEvent) => void;
    towns?: TownOption[];
    jumpToDay?: Date | null;
}

export function CalendarView({ events, onEventClick, towns = [], jumpToDay }: CalendarViewProps) {
    const [currentDate, setCurrentDate] = useState(new Date());
    const [selectedDay, setSelectedDay] = useState<Date | null>(null);

    // When a day is clicked in the mini calendar, navigate to its month and open it
    useEffect(() => {
        if (jumpToDay) {
            setCurrentDate(new Date(jumpToDay.getFullYear(), jumpToDay.getMonth(), 1));
            setSelectedDay(jumpToDay);
        }
    }, [jumpToDay]);

    const currentMonth = currentDate.getMonth();
    const currentYear = currentDate.getFullYear();

    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
    const firstDayOfMonth = new Date(currentYear, currentMonth, 1).getDay();

    const calendarDays = useMemo(() => {
        const days: (Date | null)[] = [];
        for (let i = 0; i < firstDayOfMonth; i++) {
            days.push(null);
        }
        for (let i = 1; i <= daysInMonth; i++) {
            days.push(new Date(currentYear, currentMonth, i));
        }
        return days;
    }, [currentMonth, currentYear, daysInMonth, firstDayOfMonth]);

    const monthName = currentDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

    const nextMonth = () => setCurrentDate(new Date(currentYear, currentMonth + 1, 1));
    const prevMonth = () => setCurrentDate(new Date(currentYear, currentMonth - 1, 1));

    const selectedDayEvents = useMemo(() => {
        if (!selectedDay) return [];
        return events.filter(e =>
            e.date.getDate() === selectedDay.getDate() &&
            e.date.getMonth() === selectedDay.getMonth() &&
            e.date.getFullYear() === selectedDay.getFullYear()
        );
    }, [selectedDay, events]);

    const dayHeaders = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

    return (
        <div>
            {/* Calendar header */}
            <div className="flex justify-between items-center mb-3 border-b-2 border-[var(--color-border)] pb-2">
                <button
                    onClick={prevMonth}
                    className="text-xs uppercase tracking-wider font-bold cursor-pointer bg-transparent border-none hover:text-[var(--color-accent)]"
                >
                    &larr; Prev
                </button>
                <h2 className="text-2xl font-bold">{monthName}</h2>
                <button
                    onClick={nextMonth}
                    className="text-xs uppercase tracking-wider font-bold cursor-pointer bg-transparent border-none hover:text-[var(--color-accent)]"
                >
                    Next &rarr;
                </button>
            </div>

            {/* Calendar grid */}
            <table className="w-full border-collapse border border-[var(--color-border)]">
                <thead>
                    <tr>
                        {dayHeaders.map(day => (
                            <th key={day} scope="col" className="border border-[var(--color-border)] bg-[var(--color-bg-alt)] p-1.5 text-[10px] uppercase tracking-widest font-bold text-center">
                                {day}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {Array.from({ length: Math.ceil(calendarDays.length / 7) }).map((_, weekIdx) => (
                        <tr key={weekIdx}>
                            {calendarDays.slice(weekIdx * 7, weekIdx * 7 + 7).map((day, dayIdx) => {
                                if (!day) {
                                    return <td key={`empty-${dayIdx}`} className="border border-[var(--color-border-light)] min-h-[100px] h-24 bg-[var(--color-bg-alt)]" />;
                                }

                                const dayEvents = events.filter(e =>
                                    e.date.getDate() === day.getDate() &&
                                    e.date.getMonth() === day.getMonth() &&
                                    e.date.getFullYear() === day.getFullYear()
                                );

                                return (
                                    <td
                                        key={day.toISOString()}
                                        onClick={() => setSelectedDay(day)}
                                        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedDay(day); } }}
                                        tabIndex={0}
                                        className="border border-[var(--color-border-light)] min-h-[100px] h-24 p-1.5 align-top cursor-pointer hover:bg-[var(--color-bg-alt)] transition-colors"
                                    >
                                        <div className="text-xs font-bold mb-0.5">{day.getDate()}</div>
                                        <div className="space-y-0.5">
                                            {dayEvents.slice(0, 2).map(event => (
                                                <div key={event.id} className="text-[10px] leading-tight truncate border-b border-[var(--color-border-light)] pb-0.5">
                                                    <span className="font-bold">{event.title}</span>
                                                </div>
                                            ))}
                                            {dayEvents.length > 2 && (
                                                <div className="text-[10px] italic text-[var(--color-text-muted)]">
                                                    +{dayEvents.length - 2} more...
                                                </div>
                                            )}
                                        </div>
                                    </td>
                                );
                            })}
                        </tr>
                    ))}
                </tbody>
            </table>

            {/* Day detail modal */}
            {selectedDay && (
                <Modal
                    isOpen={true}
                    onClose={() => setSelectedDay(null)}
                    title={selectedDay.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
                >
                    {selectedDayEvents.length === 0 ? (
                        <p className="text-[var(--color-text-muted)] italic py-4">No events scheduled for this day.</p>
                    ) : (
                        selectedDayEvents.map(event => (
                            <EventRow
                                key={event.id}
                                event={event}
                                onClick={onEventClick}
                                towns={towns}
                            />
                        ))
                    )}
                </Modal>
            )}
        </div>
    );
}
