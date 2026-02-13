const GUEST_DEVICE_ID_KEY = 'guest_device_id'
const GUEST_CONVERSATION_IDS_KEY = 'guest_conversation_ids'

function generateDeviceId(): string {
  return `guest_device_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
}

export function getOrCreateGuestDeviceId(): string {
  const existing = localStorage.getItem(GUEST_DEVICE_ID_KEY)
  if (existing) return existing
  const created = generateDeviceId()
  localStorage.setItem(GUEST_DEVICE_ID_KEY, created)
  return created
}

export function getGuestConversationIds(): string[] {
  try {
    const raw = localStorage.getItem(GUEST_CONVERSATION_IDS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string') : []
  } catch {
    return []
  }
}

export function rememberGuestConversationIds(ids: string[]) {
  const existing = new Set(getGuestConversationIds())
  ids.forEach((id) => {
    if (id) existing.add(id)
  })
  localStorage.setItem(GUEST_CONVERSATION_IDS_KEY, JSON.stringify(Array.from(existing)))
}

export function removeGuestConversationId(id: string) {
  if (!id) return
  const next = getGuestConversationIds().filter((x) => x !== id)
  localStorage.setItem(GUEST_CONVERSATION_IDS_KEY, JSON.stringify(next))
}

export function clearGuestIdentityData() {
  localStorage.removeItem(GUEST_DEVICE_ID_KEY)
  localStorage.removeItem(GUEST_CONVERSATION_IDS_KEY)
}
