// Central entity -> route map used to make cross-entity references (link rows,
// mail deep links, etc.) navigable. Mirrors the URL scheme the backend's
// GET /search endpoint already hands out (backend/app/api/search.py) and the
// ?open=/?workstream=/?msg= deep-link handlers read by Register.tsx,
// Topics.tsx and Mailbox.tsx — GlobalSearch itself just does
// `navigate(result.url)` with a server-supplied url, so there was no
// existing frontend map to import; this reproduces the same scheme so other
// components (LinkPanel) can link to entities client-side.
export function entityRoute(type: string, id: number | string): string | null {
  switch (type) {
    case 'action':
      return `/register?open=action-${id}`
    case 'commitment':
      return `/register?open=commitment-${id}`
    case 'topic':
      return `/topics?open=${id}`
    case 'workstream':
      return `/register?workstream=${id}`
    case 'meeting':
      return `/meetings/${id}`
    case 'key_date':
      // no item-level deep link exists on the planner page (matches the
      // fallback the backend search endpoint uses for the same type)
      return '/planner'
    case 'decision':
    case 'forum':
      // decisions route through their meeting, but Link rows don't carry the
      // meeting id without an extra fetch — land on the meetings list
      return '/meetings'
    case 'mail':
      return `/mailbox?msg=${id}`
    case 'person':
      return `/people/${id}/pack`
    case 'person_note':
      // resolving a note -> person would need an extra fetch this map
      // deliberately avoids; land on the people list instead
      return '/people'
    case 'discussion_point':
      // same limitation as person_note: no person id without an extra fetch
      return '/people'
    default:
      return null
  }
}
