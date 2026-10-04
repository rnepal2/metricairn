import { useCallback, useEffect, useRef, useState } from 'react'

export function useFetch<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const generation = useRef(0)
  const load = useCallback(async () => {
    const request = ++generation.current
    setLoading(true)
    setError('')
    setData(null)
    try {
      const result = await fn()
      if (request === generation.current) setData(result)
    } catch (e) {
      if (request === generation.current)
        setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      if (request === generation.current) setLoading(false)
    }
  }, deps)
  useEffect(() => {
    void load()
    return () => {
      generation.current++
    }
  }, [load])
  return { data, loading, error, reload: load }
}
