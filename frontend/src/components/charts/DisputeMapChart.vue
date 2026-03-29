<template>
  <div class="chart-wrapper">
    <h3 class="chart-title">Dispute Map</h3>
    <div v-if="disputes.length === 0" class="chart-empty">
      <p>No contested triples found.</p>
    </div>
    <Bar v-else :data="chartData" :options="chartOptions" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Bar } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale } from 'chart.js'

ChartJS.register(Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale)

const props = defineProps({
  disputes: { type: Array, default: () => [] },
})

const chartData = computed(() => ({
  labels: props.disputes.map(d => {
    const claim = d.claim || ''
    return claim.length > 40 ? claim.substring(0, 40) + '...' : claim
  }),
  datasets: [
    {
      label: 'Upvotes',
      data: props.disputes.map(d => d.upvotes || 0),
      backgroundColor: 'rgba(26, 147, 111, 0.7)',
      borderColor: 'rgba(26, 147, 111, 1)',
      borderWidth: 1,
    },
    {
      label: 'Downvotes',
      data: props.disputes.map(d => d.downvotes || 0),
      backgroundColor: 'rgba(239, 68, 68, 0.7)',
      borderColor: 'rgba(239, 68, 68, 1)',
      borderWidth: 1,
    },
  ],
}))

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'top' },
    tooltip: {
      callbacks: {
        title: (items) => {
          const idx = items[0]?.dataIndex
          return props.disputes[idx]?.claim || ''
        },
      },
    },
  },
  scales: {
    x: { ticks: { maxRotation: 45 } },
    y: { beginAtZero: true, title: { display: true, text: 'Votes' } },
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
