import { useState, useEffect, useRef } from 'react'

const CORRECT_PIN = '557799'
const STORAGE_KEY = 'eva_pin_verified'

function verifyPin(pin: string): boolean {
  if (pin === CORRECT_PIN) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ timestamp: Date.now() }))
    return true
  }
  return false
}

export function PinGate({ onVerified }: { onVerified: () => void }) {
  const [digits, setDigits] = useState<string[]>(Array(6).fill(''))
  const [error, setError] = useState(false)
  const [shake, setShake] = useState(false)
  const inputsRef = useRef<(HTMLInputElement | null)[]>([])

  const handleChange = (index: number, value: string) => {
    if (!/^\d*$/.test(value)) return
    const newDigits = [...digits]
    newDigits[index] = value.slice(-1)
    setDigits(newDigits)
    setError(false)

    if (value && index < 5) {
      inputsRef.current[index + 1]?.focus()
    }

    // Auto-submit when all 6 filled
    const filled = newDigits.join('')
    if (filled.length === 6) {
      const ok = verifyPin(filled)
      if (ok) {
        onVerified()
      } else {
        setError(true)
        setShake(true)
        setTimeout(() => {
          setShake(false)
          setDigits(Array(6).fill(''))
          inputsRef.current[0]?.focus()
        }, 600)
      }
    }
  }

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !digits[index] && index > 0) {
      inputsRef.current[index - 1]?.focus()
    }
  }

  useEffect(() => {
    inputsRef.current[0]?.focus()
  }, [])

  return (
    <div className="min-h-screen bg-white flex flex-col items-center justify-center gap-8">
      {/* Radar animation */}
      <div className="relative flex items-center justify-center">
        <div className="radar-pulse w-20 h-20 rounded-full" />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-mono text-cyan-400 text-2xl font-bold tracking-widest">EVA</span>
        </div>
      </div>

      <div className="flex flex-col items-center gap-2">
        <div className="font-mono text-xs text-gray-500 tracking-widest uppercase">
          Revenue-First Operator Console
        </div>
        <div className="font-mono text-xs text-gray-500 tracking-wider">
          Mangotec LLC · Restricted Access
        </div>
      </div>

      <div className={`flex flex-col items-center gap-6 ${shake ? 'animate-shake' : ''}`}>
        <div className="font-mono text-sm text-gray-500 tracking-widest">ENTER PIN</div>

        <div className="flex gap-3">
          {digits.map((d, i) => (
            <input
              key={i}
              ref={el => { inputsRef.current[i] = el }}
              type="password"
              inputMode="numeric"
              maxLength={1}
              value={d}
              onChange={e => handleChange(i, e.target.value)}
              onKeyDown={e => handleKeyDown(i, e)}
              className={`w-11 h-14 text-center text-xl font-mono rounded-lg border bg-gray-50 text-white outline-none transition-all
                ${error
                  ? 'border-red-500 text-red-400'
                  : d
                    ? 'border-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.3)]'
                    : 'border-gray-200 focus:border-cyan-600'
                }`}
            />
          ))}
        </div>

        {error && (
          <div className="font-mono text-xs text-red-400 tracking-widest animate-fade-in">
            ACCESS DENIED
          </div>
        )}
      </div>

      <div className="font-mono text-xs text-gray-400 tracking-wider mt-4">
        Session valid for 8 hours
      </div>
    </div>
  )
}
