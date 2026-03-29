<template>
  <div class="chart-wrapper">
    <h3 class="chart-title">Graph Growth</h3>
    <div v-if="!data || data.length === 0" class="chart-empty">
      <p>No graph growth data available.</p>
    </div>
    <Line v-else :data="chartData" :options="chartOptions" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale, Filler } from 'chart.js'

ChartJS.register(Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale, Filler)

const props = defineProps({
  data: { type: Array, default: () => [] },
})

const chartData = computed(() => {
  const labels = props.data.map(d => `R${d.round}`)
  return {
    labels,
    datasets: [
      {
        label: 'Pending',
        data: props.data.map(d => d.pending || 0),
        backgroundColor: 'rgba(245, 158, 11, 0.3)',
        borderColor: 'rgba(245, 158, 11, 1)',
        fill: true,
        tension: 0.3,
      },
      {
        label: 'Accepted',
        data: props.data.map(d => d.accepted || 0),
        backgroundColor: 'rgba(26, 147, 111, 0.3)',
        borderColor: 'rgba(26, 147, 111, 1)',
        fill: true,
        tension: 0.3,
      },
      {
        label: 'Contested',
        data: props.data.map(d => d.contested || 0),
        backgroundColor: 'rgba(255, 69, 0, 0.3)',
        borderColor: 'rgba(255, 69, 0, 1)',
        fill: true,
        tension: 0.3,
      },
      {
        label: 'Pruned',
        data: props.data.map(d => d.pruned || 0),
        backgroundColor: 'rgba(153, 153, 153, 0.3)',
        borderColor: 'rgba(153, 153, 153, 1)',
        fill: true,
        tension: 0.3,
      },
    ],
  }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'top' },
  },
  scales: {
    y: {
      stacked: true,
      beginAtZero: true,
      title: { display: true, text: 'Triples' },
    },
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
