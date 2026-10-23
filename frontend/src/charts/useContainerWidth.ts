import { useEffect, useRef, useState, type RefObject } from 'react'

const MIN_WIDTH = 280

/** Pixel width of a container, kept in sync with resizes, so SVG text renders at a constant size. */
export function useContainerWidth(fallback: number): { ref: RefObject<HTMLDivElement | null>; width: number } {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(fallback)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const update = () => setWidth(Math.max(MIN_WIDTH, Math.round(el.getBoundingClientRect().width)))
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return { ref, width }
}
