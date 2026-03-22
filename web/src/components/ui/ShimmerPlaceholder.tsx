interface ShimmerPlaceholderProps {
  width?: string | number;
  height?: string | number;
  className?: string;
  rounded?: boolean;
}

export function ShimmerPlaceholder({
  width = '100%',
  height = '100%',
  className = '',
  rounded = true,
}: ShimmerPlaceholderProps) {
  return (
    <div
      className={`shimmer ${rounded ? 'rounded-2xl' : ''} ${className}`}
      style={{
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof height === 'number' ? `${height}px` : height,
      }}
    />
  );
}
