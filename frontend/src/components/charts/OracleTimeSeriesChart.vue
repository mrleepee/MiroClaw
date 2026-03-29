<template>
  <div class="chart-wrapper">
    <h3 class="chart-title">Oracle Forecast Time Series</h3>
    <div v-if="series.length === 0" class="chart-empty">
      <p>No oracle forecasts recorded.</p>
    </div>
    <Line v-else :data="chartData" :options="chartOptions" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale, Filler } from 'chart.js'

ChartJS.register(Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale, Filler)

const colors = ['#FF4500', '#3B82F6', '#8B5CF6', '#F59E0B']

const props = defineProps({
  series: { type: Array, default: () => [] },
})

const chartData = computed(() => {
  const allRounds = new Set()
  props.series.forEach(s => {
    Object.values(s.questions || {}).forEach(points => {
      points.forEach(p => allRounds.add(p.round))
    })
  })
  const rounds = [...allRounds].sort((a, b) => a - b)
  const labels = rounds.map(r => `R${r}`)

  const datasets = []
  props.series.forEach((oracle, oi) => {
    Object.entries(oracle.questions || {}).forEach(([q, points], qi) => {
      const dataMap = Object.fromEntries(points.map(p => [p.round, p.probability]))
      datasets.push({
        label: `${oracle.oracle_id}: ${q.length > 50 ? q.substring(0, 50) + '...' : q}`,
        data: rounds.map(r => dataMap[r] ?? null),
        borderColor: colors[(oi + qi) % colors.length],
        backgroundColor: colors[(oi + qi) % colors.length] + '20',
        tension: 0.3,
        spanGaps: true,
        fill: false,
      })
    })
  })

  return { labels, datasets }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'top', labels: { boxWidth: 12 } },
  },
  scales: {
    y: { min: 0, max: 1, title: { display: true, text: 'Probability' } },
    x: { title: { display: true, text: 'Round' } },
  },
}
</script>

<style scoped>
.chart-wrapper {
  background: var(--color-bg-surface, #FAFAFA);
  border: 1px solid var(--color-border, #EAEAEA);
  border-radius: var(--radius-lg, 10px);
  padding: 24px;
}
.chart-title {
  font-family: var(--font-sans, 'Space Grotesk', sans-serif);
  font-size: 1.1rem;
  margin-bottom: 16px;
  color: var(--color-text-primary, #000);
}
.chart-empty {
  text-align: center;
  padding: 40px 0;
  color: var(--color-text-tertiary, #999);
}
</style>
