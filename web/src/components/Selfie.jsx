import { useEffect, useRef, useState } from 'react'

// Your camera, for realism and self-review. The stream is attached to a local
// <video> and never leaves the browser — it is not uploaded, recorded, or scored.
// Body language is deliberately not an input to this product.
export default function Selfie() {
  const videoRef = useRef(null)
  const [state, setState] = useState('starting')

  useEffect(() => {
    let stream = null
    let cancelled = false

    navigator.mediaDevices
      ?.getUserMedia({ video: { width: 640, height: 480 }, audio: false })
      .then((granted) => {
        if (cancelled) {
          granted.getTracks().forEach((t) => t.stop())
          return
        }
        stream = granted
        if (videoRef.current) videoRef.current.srcObject = granted
        setState('live')
      })
      .catch(() => {
        if (!cancelled) setState('off')
      })

    return () => {
      cancelled = true
      stream?.getTracks().forEach((t) => t.stop())
    }
  }, [])

  return (
    <div className="selfie">
      {state === 'live' ? (
        <video ref={videoRef} autoPlay playsInline muted aria-label="Your camera" />
      ) : (
        <p className="off">{state === 'starting' ? 'Camera…' : 'Camera off'}</p>
      )}
    </div>
  )
}
