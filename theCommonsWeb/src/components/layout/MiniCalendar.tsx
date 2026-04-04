import { useState, useMemo } from 'react';
import type { FrontendEvent } from '../../models/eventsModels';

interface MiniCalendarProps {
    events: FrontendEvent[];
    selectedDate: Date | null;
    onDayClick: (date: Date | null) => void;
}

function isSameDay(a: Date, b: Date) {
    return (
        a.getDate() === b.getDate() &&
        a.getMonth() === b.getMonth() &&
        a.getFullYear() === b.getFullYear()
    );
}

export function MiniCalendar({ events, selectedDate, onDayClick }: MiniCalendarProps) {
    const today = useMemo(() => new Date(), []);

    const [viewDate, setViewDate] = useState(() => {
        const d = new Date();
        d.setDate(1);
        return d;
    });

    const month = viewDate.getMonth();
    const year = viewDate.getFullYear();

    const monthLabel = viewDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

    const prevMonth = () => setViewDate(new Date(year, month - 1, 1));
    const nextMonth = () => setViewDate(new Date(year, month + 1, 1));

    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const firstDow = new Date(year, month, 1).getDay();

    // Which days this month have events
    const eventDayNums = useMemo(() => {
        const set = new Set<number>();
        for (const e of events) {
            if (e.date.getMonth() === month && e.date.getFullYear() === year) {
                set.add(e.date.getDate());
            }
        }
        return set;
    }, [events, month, year]);

    // Build week rows
    const weeks = useMemo(() => {
        const rows: (number | null)[][] = [];
        let row: (number | null)[] = Array(firstDow).fill(null);
        for (let d = 1; d <= daysInMonth; d++) {
            row.push(d);
            if (row.length === 7) {
                rows.push(row);
                row = [];
            }
        }
        if (row.length > 0) {
            while (row.length < 7) row.push(null);
            rows.push(row);
        }
        return rows;
    }, [firstDow, daysInMonth]);

    const DOW_LABELS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

    return (
        <div>
            {/* Month navigation */}
            <div className="flex items-center justify-between mb-2">
                <button
                    onClick={prevMonth}
                    className="text-[10px] cursor-pointer bg-transparent border-none hover:text-[var(--color-accent)] leading-none p-0"
                    aria-label="Previous month"
                >
                    ←
                </button>
                <p className="text-[9px] uppercase tracking-[0.18em] font-black">
                    {monthLabel}
                </p>
                <button
                    onClick={nextMonth}
                    className="text-[10px] cursor-pointer bg-transparent border-none hover:text-[var(--color-accent)] leading-none p-0"
                    aria-label="Next month"
                >
                    →
                </button>
            </div>

            {/* Grid */}
            <table className="w-full text-center border-collapse" role="grid" aria-label={`Calendar for ${monthLabel}`}>
                <thead>
                    <tr>
                        {DOW_LABELS.map((d, i) => (
                            <th
                                key={i}
                                scope="col"
                                className="text-[8px] font-bold text-[var(--color-text-muted)] pb-1 w-[14.28%]"
                            >
                                {d}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {weeks.map((week, wi) => (
                        <tr key={wi}>
                            {week.map((day, di) => {
                                if (!day) return <td key={di} className="h-5" />;

                                const date = new Date(year, month, day);
                                const isToday = isSameDay(date, today);
                                const isSelected = selectedDate ? isSameDay(date, selectedDate) : false;
                                const hasEvents = eventDayNums.has(day);

                                return (
                                    <td key={di} className="h-5 relative">
                                        <button
                                            onClick={() => onDayClick(isSelected ? null : date)}
                                            className={[
                                                'w-5 h-5 text-[9px] rounded-sm cursor-pointer border-none',
                                                'inline-flex items-center justify-center transition-colors relative',
                                                isSelected
                                                    ? 'bg-[var(--color-accent)] text-white font-black'
                                                    : isToday
                                                        ? 'font-black underline decoration-[var(--color-accent)] hover:text-[var(--color-accent)]'
                                                        : 'bg-transparent hover:bg-[var(--color-bg-alt)] hover:text-[var(--color-accent)]',
                                            ].join(' ')}
                                            aria-label={`${date.toLocaleDateString('en-US', { month: 'long', day: 'numeric' })}${hasEvents ? ', has events' : ''}`}
                                            aria-pressed={isSelected}
                                        >
                                            {day}
                                            {hasEvents && !isSelected && (
                                                <span
                                                    className="absolute bottom-px left-1/2 -translate-x-1/2 w-0.5 h-0.5 rounded-full bg-[var(--color-accent)]"
                                                    aria-hidden="true"
                                                />
                                            )}
                                        </button>
                                    </td>
                                );
                            })}
                        </tr>
                    ))}
                </tbody>
            </table>

            {selectedDate && (
                <p className="text-center mt-1.5">
                    <button
                        onClick={() => onDayClick(null)}
                        className="text-[8px] uppercase tracking-wider italic underline cursor-pointer bg-transparent border-none hover:text-[var(--color-accent)]"
                    >
                        clear date
                    </button>
                </p>
            )}
        </div>
    );
}
