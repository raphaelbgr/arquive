import { useState, useEffect, useRef, useCallback } from 'react';
import { motion } from 'framer-motion';
import type { EPGProgram, Channel } from '../../types';
import { api } from '../../api/client';
import { GlassCard } from '../ui/GlassCard';
import { ProgramCard } from './ProgramCard';

/**
 * Custom-built EPG (Electronic Program Guide) grid.
 *
 * Uses Canvas for the timeline grid rendering (60fps, thousands of programs)
 * with a channel list on the left. Supports horizontal scrolling (time axis)
 * and vertical scrolling (channels).
 *
 * MIT licensed -- does NOT use planby or any proprietary EPG library.
 */

const HOUR_WIDTH = 240;
const ROW_HEIGHT = 64;
const CHANNEL_COL_WIDTH = 160;
const HOURS_VISIBLE = 6;
const CANVAS_PADDING = 1;

const CATEGORY_COLORS: Record<string, string> = {
  sports: '#34D399',
  news: '#60A5FA',
  movie: '#F87171',
  movies: '#F87171',
  entertainment: '#A78BFA',
  kids: '#FBBF24',
  music: '#F472B6',
  documentary: '#2DD4BF',
};

function getTimeRange(date: Date): { start: Date; end: Date } {
  const start = new Date(date);
  start.setMinutes(0, 0, 0);
  const end = new Date(start);
  end.setHours(start.getHours() + HOURS_VISIBLE);
  return { start, end };
}

function formatHour(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

interface EPGGridProps {
  channels: Channel[];
  onProgramClick?: (program: EPGProgram) => void;
  onChannelClick?: (channel: Channel) => void;
}

export function EPGGrid({ channels, onProgramClick, onChannelClick }: EPGGridProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [programs, setPrograms] = useState<EPGProgram[]>([]);
  const [scrollX, setScrollX] = useState(0);
  const [scrollY, setScrollY] = useState(0);
  const [baseTime, setBaseTime] = useState(() => new Date());
  const [nowPrograms, setNowPrograms] = useState<EPGProgram[]>([]);
  const [selectedProgram, setSelectedProgram] = useState<EPGProgram | null>(null);

  const { start: timeStart, end: timeEnd } = getTimeRange(baseTime);

  // Fetch EPG data
  const dateKey = timeStart.toISOString().slice(0, 10);
  useEffect(() => {
    api.iptv
      .epg({ date: dateKey, limit: '2000' })
      .then((data) => setPrograms((data.programs ?? []) as unknown as EPGProgram[]))
      .catch(() => {});
    api.iptv
      .epgNow()
      .then((data) => setNowPrograms((data.programs ?? []) as unknown as EPGProgram[]))
      .catch(() => {});
  }, [dateKey]);

  // Build program map by channel
  const programsByChannel = useRef(new Map<string, EPGProgram[]>());
  useEffect(() => {
    const map = new Map<string, EPGProgram[]>();
    for (const p of programs) {
      const list = map.get(p.channel_id) || [];
      list.push(p);
      map.set(p.channel_id, list);
    }
    programsByChannel.current = map;
  }, [programs]);

  // Canvas rendering
  const drawGrid = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    const totalWidth = HOURS_VISIBLE * HOUR_WIDTH;
    const now = new Date();
    const timeStartMs = timeStart.getTime();
    const timeEndMs = timeEnd.getTime();
    const totalMs = timeEndMs - timeStartMs;

    // Hour lines
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 1;
    for (let h = 0; h <= HOURS_VISIBLE; h++) {
      const x = h * HOUR_WIDTH - scrollX;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }

    // Half-hour lines
    ctx.strokeStyle = 'rgba(255,255,255,0.03)';
    for (let h = 0; h < HOURS_VISIBLE; h++) {
      const x = h * HOUR_WIDTH + HOUR_WIDTH / 2 - scrollX;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }

    // Program blocks per channel row
    for (let i = 0; i < channels.length; i++) {
      const ch = channels[i];
      const y = i * ROW_HEIGHT - scrollY;
      if (y + ROW_HEIGHT < 0 || y > height) continue;

      // Row background (alternating)
      ctx.fillStyle = i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.04)';
      ctx.fillRect(0, y, totalWidth, ROW_HEIGHT);

      ctx.strokeStyle = 'rgba(255,255,255,0.05)';
      ctx.beginPath();
      ctx.moveTo(0, y + ROW_HEIGHT);
      ctx.lineTo(totalWidth, y + ROW_HEIGHT);
      ctx.stroke();

      const channelProgs = programsByChannel.current.get(ch.tvg_id || '') || [];
      for (const prog of channelProgs) {
        const progStart = new Date(prog.start_time).getTime();
        const progEnd = new Date(prog.end_time).getTime();
        if (progEnd < timeStartMs || progStart > timeEndMs) continue;

        const xStart = Math.max(0, ((progStart - timeStartMs) / totalMs) * totalWidth) - scrollX;
        const xEnd = Math.min(totalWidth, ((progEnd - timeStartMs) / totalMs) * totalWidth) - scrollX;
        const progWidth = xEnd - xStart;
        if (progWidth < 2) continue;

        const category = (prog.category || '').toLowerCase();
        const color = CATEGORY_COLORS[category] || '#9CA3AF';
        const isNow = progStart <= now.getTime() && progEnd > now.getTime();

        // Program block
        ctx.fillStyle = isNow ? `${color}33` : `${color}18`;
        ctx.beginPath();
        ctx.roundRect(xStart + CANVAS_PADDING, y + 4, progWidth - CANVAS_PADDING * 2, ROW_HEIGHT - 8, 6);
        ctx.fill();

        // Left accent
        ctx.fillStyle = `${color}${isNow ? 'CC' : '66'}`;
        ctx.beginPath();
        ctx.roundRect(xStart + CANVAS_PADDING, y + 4, 3, ROW_HEIGHT - 8, [3, 0, 0, 3]);
        ctx.fill();

        // Title text
        ctx.fillStyle = isNow ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.5)';
        ctx.font = `${isNow ? '600' : '400'} 11px Inter, system-ui, sans-serif`;
        const maxTextWidth = progWidth - 14;
        if (maxTextWidth > 20) {
          ctx.save();
          ctx.beginPath();
          ctx.rect(xStart + 10, y, maxTextWidth, ROW_HEIGHT);
          ctx.clip();
          ctx.fillText(prog.title, xStart + 10, y + ROW_HEIGHT / 2 - 2);
          ctx.fillStyle = 'rgba(255,255,255,0.2)';
          ctx.font = '400 9px Inter, system-ui, sans-serif';
          ctx.fillText(
            `${formatHour(new Date(prog.start_time))} - ${formatHour(new Date(prog.end_time))}`,
            xStart + 10,
            y + ROW_HEIGHT / 2 + 12,
          );
          ctx.restore();
        }

        // Now-playing progress
        if (isNow) {
          const progress = (now.getTime() - progStart) / (progEnd - progStart);
          ctx.fillStyle = `${color}44`;
          ctx.beginPath();
          ctx.roundRect(xStart + CANVAS_PADDING, y + ROW_HEIGHT - 6, (progWidth - CANVAS_PADDING * 2) * progress, 2, 1);
          ctx.fill();
        }
      }
    }

    // Current time marker (red line)
    const nowMs = now.getTime();
    if (nowMs >= timeStartMs && nowMs <= timeEndMs) {
      const nowX = ((nowMs - timeStartMs) / totalMs) * totalWidth - scrollX;
      ctx.strokeStyle = '#EF4444';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(nowX, 0);
      ctx.lineTo(nowX, height);
      ctx.stroke();
      ctx.fillStyle = '#EF4444';
      ctx.beginPath();
      ctx.arc(nowX, 4, 4, 0, Math.PI * 2);
      ctx.fill();
    }
  }, [channels, scrollX, scrollY, timeStart, timeEnd, programs]);

  useEffect(() => {
    drawGrid();
    const interval = setInterval(drawGrid, 30000);
    return () => clearInterval(interval);
  }, [drawGrid]);

  const handleWheel = (e: React.WheelEvent) => {
    if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
      setScrollX((prev) => Math.max(0, prev + (e.deltaX || e.deltaY)));
    } else {
      setScrollY((prev) => Math.max(0, Math.min(channels.length * ROW_HEIGHT - 400, prev + e.deltaY)));
    }
  };

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left + scrollX;
    const y = e.clientY - rect.top + scrollY;
    const channelIndex = Math.floor(y / ROW_HEIGHT);
    if (channelIndex < 0 || channelIndex >= channels.length) return;

    const ch = channels[channelIndex];
    const channelProgs = programsByChannel.current.get(ch.tvg_id || '') || [];
    const timeStartMs = timeStart.getTime();
    const totalMs = timeEnd.getTime() - timeStartMs;
    const totalWidth = HOURS_VISIBLE * HOUR_WIDTH;
    const clickTimeMs = timeStartMs + (x / totalWidth) * totalMs;

    for (const prog of channelProgs) {
      const pStart = new Date(prog.start_time).getTime();
      const pEnd = new Date(prog.end_time).getTime();
      if (clickTimeMs >= pStart && clickTimeMs < pEnd) {
        setSelectedProgram(prog);
        onProgramClick?.(prog);
        return;
      }
    }
  };

  const shiftTime = (hours: number) => {
    setBaseTime((prev) => {
      const next = new Date(prev);
      next.setHours(prev.getHours() + hours);
      return next;
    });
    setScrollX(0);
  };

  return (
    <div className="space-y-3">
      {/* Time nav header */}
      <GlassCard className="p-3" hover={false}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => shiftTime(-HOURS_VISIBLE)}
              className="px-3 py-1.5 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] bg-[var(--glass-bg)] rounded-lg transition-colors"
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => { setBaseTime(new Date()); setScrollX(0); }}
              className="px-3 py-1.5 text-xs text-[#007AFF] bg-[#007AFF]/10 rounded-lg hover:bg-[#007AFF]/20 transition-colors font-medium"
            >
              Now
            </button>
            <button
              type="button"
              onClick={() => shiftTime(HOURS_VISIBLE)}
              className="px-3 py-1.5 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] bg-[var(--glass-bg)] rounded-lg transition-colors"
            >
              Next
            </button>
          </div>
          <div className="text-xs text-[var(--text-secondary)] font-medium">
            {timeStart.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })}
            {' '}
            {formatHour(timeStart)} - {formatHour(timeEnd)}
          </div>
          <div className="text-[10px] text-[var(--text-tertiary)]">
            {channels.length} channels / {programs.length} programs
          </div>
        </div>
      </GlassCard>

      {/* EPG Grid */}
      <div className="flex rounded-2xl overflow-hidden border border-[var(--glass-border)]">
        {/* Channel column */}
        <div className="shrink-0 bg-[var(--glass-bg)] border-r border-white/10 overflow-hidden" style={{ width: CHANNEL_COL_WIDTH }}>
          <div className="h-8 border-b border-white/10 flex items-center px-3">
            <span className="text-[10px] text-[var(--text-tertiary)] font-medium">Channels</span>
          </div>
          <div style={{ transform: `translateY(-${scrollY}px)` }}>
            {channels.map((ch) => (
              <button
                key={ch.id}
                type="button"
                onClick={() => onChannelClick?.(ch)}
                className="w-full flex items-center gap-2 px-3 border-b border-[var(--glass-border)] hover:bg-[var(--glass-hover-bg)] transition-colors text-left"
                style={{ height: ROW_HEIGHT }}
              >
                {ch.logo_url ? (
                  <img src={ch.logo_url} alt="" className="w-6 h-6 rounded object-contain bg-[var(--glass-bg)]" />
                ) : (
                  <div className="w-6 h-6 rounded bg-[var(--glass-bg)] flex items-center justify-center text-[8px] text-[var(--text-tertiary)] font-bold">
                    {ch.name.charAt(0)}
                  </div>
                )}
                <span className="text-[11px] text-[var(--text-secondary)] truncate">{ch.name}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Timeline canvas */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="h-8 border-b border-white/10 flex shrink-0 overflow-hidden">
            <div className="flex" style={{ transform: `translateX(-${scrollX}px)` }}>
              {Array.from({ length: HOURS_VISIBLE }).map((_, i) => {
                const hourDate = new Date(timeStart);
                hourDate.setHours(timeStart.getHours() + i);
                return (
                  <div key={i} className="shrink-0 flex items-center px-3 border-r border-white/5" style={{ width: HOUR_WIDTH }}>
                    <span className="text-[10px] text-[var(--text-tertiary)] font-medium tabular-nums">{formatHour(hourDate)}</span>
                  </div>
                );
              })}
            </div>
          </div>
          <div
            ref={containerRef}
            className="relative overflow-hidden cursor-crosshair"
            style={{ height: Math.min(channels.length * ROW_HEIGHT, 480) }}
            onWheel={handleWheel}
          >
            <canvas ref={canvasRef} className="w-full h-full" onClick={handleCanvasClick} />
          </div>
        </div>
      </div>

      {/* Now playing summary */}
      {nowPrograms.length > 0 && (
        <GlassCard className="p-4" hover={false}>
          <h3 className="text-xs font-semibold text-[var(--text-secondary)] mb-3">Now Playing</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {nowPrograms.slice(0, 6).map((prog) => (
              <ProgramCard key={prog.id} program={prog} isNowPlaying onClick={() => { setSelectedProgram(prog); onProgramClick?.(prog); }} />
            ))}
          </div>
        </GlassCard>
      )}

      {/* Selected program detail */}
      {selectedProgram && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mt-2">
          <GlassCard className="p-4" hover={false}>
            <div className="flex justify-between items-start">
              <div>
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">{selectedProgram.title}</h3>
                {selectedProgram.subtitle && <p className="text-xs text-[var(--text-tertiary)] mt-0.5">{selectedProgram.subtitle}</p>}
                <p className="text-xs text-[var(--text-tertiary)] mt-2">{selectedProgram.description}</p>
                <div className="flex items-center gap-3 mt-2">
                  <span className="text-[10px] text-[var(--text-tertiary)]">
                    {formatHour(new Date(selectedProgram.start_time))} - {formatHour(new Date(selectedProgram.end_time))}
                  </span>
                  {selectedProgram.category && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--glass-bg)] text-[var(--text-tertiary)]">{selectedProgram.category}</span>
                  )}
                </div>
              </div>
              <button type="button" onClick={() => setSelectedProgram(null)} className="text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]">Close</button>
            </div>
          </GlassCard>
        </motion.div>
      )}
    </div>
  );
}
