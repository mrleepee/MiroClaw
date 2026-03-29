<template>
  <div class="provenance-trail">
    <div class="trail-header">
      <h3 class="trail-title">Provenance Trail</h3>
      <div class="trail-filters">
        <button
          v-for="filter in filters"
          :key="filter.key"
          class="filter-btn"
          :class="{ active: activeFilter === filter.key }"
          @click="activeFilter = filter.key"
        >{{ filter.label }}</button>
      </div>
    </div>

    <div v-if="filteredEntries.length === 0" class="trail-empty">
      <p>No provenance entries available.</p>
    </div>

    <div v-else class="trail-timeline">
      <div
        v-for="(entry, idx) in filteredEntries"
        :key="idx"
        class="trail-entry"
        :class="'entry-type-' + entry.action_type"
      >
        <div class="entry-connector">
          <div class="entry-dot"></div>
          <div class="entry-line" v-if="idx < filteredEntries.length - 1"></div>
        </div>
        <div class="entry-content">
          <div class="entry-header">
            <span class="entry-type-badge">{{ formatActionType(entry.action_type) }}</span>
            <span class="entry-round">Round {{ entry.round }}</span>
            <span class="entry-time">{{ entry.timestamp }}</span>
          </div>
          <div class="entry-detail" v-if="expandedEntries.has(idx)" @click="toggleEntry(idx)">
            <p v-if="entry.query" class="entry-field"><strong>Query:</strong> {{ entry.query }}</p>
            <p v-if="entry.url" class="entry-field"><strong>URL:</strong> {{ entry.url }}</p>
            <p v-if="entry.triple" class="entry-field"><strong>Triple:</strong> {{ entry.triple }}</p>
            <p v-if="entry.direction" class="entry-field"><strong>Vote:</strong> {{ entry.direction }}</p>
            <p v-if="entry.question" class="entry-field"><strong>Oracle Question:</strong> {{ entry.question }}</p>
            <p v-if="entry.probability" class="entry-field"><strong>Probability:</strong> {{ (entry.probability * 100).toFixed(1) }}%</p>
            <p v-if="entry.stance_from" class="entry-field"><strong>Stance Shift:</strong> {{ entry.stance_from }} &rarr; {{ entry.stance_to }}</p>
            <p v-if="entry.evidence" class="entry-field"><strong>Evidence:</strong> {{ entry.evidence }}</p>
          </div>
          <div v-else class="entry-summary" @click="toggleEntry(idx)">
            {{ getEntrySummary(entry) }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  entries: { type: Array, default: () => [] },
})

const activeFilter = ref('all')
const expandedEntries = ref(new Set())

const filters = [
  { key: 'all', label: 'All' },
  { key: 'search', label: 'Searches' },
  { key: 'read', label: 'Reads' },
  { key: 'triple', label: 'Triples' },
  { key: 'vote', label: 'Votes' },
  { key: 'oracle', label: 'Oracle' },
  { key: 'stance_shift', label: 'Stance Shifts' },
]

const filteredEntries = computed(() => {
  if (activeFilter.value === 'all') return props.entries
  return props.entries.filter(e => e.action_type === activeFilter.value)
})

const toggleEntry = (idx) => {
  const s = new Set(expandedEntries.value)
  if (s.has(idx)) s.delete(idx)
  else s.add(idx)
  expandedEntries.value = s
}

const formatActionType = (type) => {
  const map = {
    search: 'SEARCH',
    read: 'READ',
    triple: 'TRIPLE',
    vote: 'VOTE',
    oracle: 'ORACLE',
    stance_shift: 'SHIFT',
  }
  return map[type] || type?.toUpperCase()
}

const getEntrySummary = (entry) => {
  if (entry.query) return entry.query.length > 80 ? entry.query.substring(0, 80) + '...' : entry.query
  if (entry.url) return entry.url.length > 80 ? entry.url.substring(0, 80) + '...' : entry.url
  if (entry.triple) return entry.triple.length > 80 ? entry.triple.substring(0, 80) + '...' : entry.triple
  if (entry.stance_from) return `${entry.stance_from} → ${entry.stance_to}`
  return entry.action_type || 'Action'
}
</script>

<style scoped>
.provenance-trail {
  background: var(--color-bg-surface, #FAFAFA);
  border: 1px solid var(--color-border, #EAEAEA);
  border-radius: var(--radius-lg, 10px);
  padding: 24px;
}

.trail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.trail-title {
  font-family: var(--font-sans, 'Space Grotesk', sans-serif);
  font-size: 1.1rem;
  color: var(--color-text-primary, #000);
}

.trail-filters {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.filter-btn {
  padding: 4px 10px;
  border: 1px solid var(--color-border, #EAEAEA);
  background: transparent;
  color: var(--color-text-secondary, #666);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  border-radius: var(--radius-sm, 2px);
  font-family: var(--font-sans, 'Space Grotesk', sans-serif);
  transition: all 0.2s ease;
}

.filter-btn:hover {
  background: var(--color-bg-elevated, #F5F5F5);
}

.filter-btn.active {
  background: var(--color-text-primary, #000);
  color: #FFF;
  border-color: transparent;
}

.trail-empty {
  text-align: center;
  padding: 40px 0;
  color: var(--color-text-tertiary, #999);
}

.trail-timeline {
  display: flex;
  flex-direction: column;
}

.trail-entry {
  display: flex;
  gap: 12px;
}

.entry-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 16px;
  flex-shrink: 0;
}

.entry-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-border, #CCC);
  flex-shrink: 0;
  margin-top: 6px;
}

.entry-type-search .entry-dot { background: #6366F1; }
.entry-type-read .entry-dot { background: #8B5CF6; }
.entry-type-triple .entry-dot { background: var(--color-accent, #FF4500); }
.entry-type-vote .entry-dot { background: #F59E0B; }
.entry-type-oracle .entry-dot { background: #1A936F; }
.entry-type-stance_shift .entry-dot { background: #EF4444; }

.entry-line {
  width: 1px;
  flex: 1;
  background: var(--color-border, #EAEAEA);
  min-height: 8px;
}

.entry-content {
  flex: 1;
  padding-bottom: 12px;
}

.entry-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.entry-type-badge {
  font-size: 9px;
  font-weight: 700;
  background: var(--color-bg-elevated, #F0F0F0);
  padding: 1px 6px;
  border-radius: 2px;
  color: var(--color-text-secondary, #666);
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
}

.entry-round {
  font-size: 10px;
  color: var(--color-text-tertiary, #999);
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
}

.entry-time {
  font-size: 10px;
  color: var(--color-text-tertiary, #999);
}

.entry-summary,
.entry-detail {
  font-size: 12px;
  color: var(--color-text-secondary, #555);
  cursor: pointer;
  padding: 4px 0;
  line-height: 1.5;
}

.entry-detail {
  background: var(--color-bg-elevated, #F5F5F5);
  padding: 8px 12px;
  border-radius: var(--radius-sm, 2px);
}

.entry-field {
  margin: 2px 0;
  font-size: 12px;
}
</style>
