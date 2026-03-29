<template>
  <div class="chart-wrapper">
    <h3 class="chart-title">Position Drift</h3>
    <div v-if="agents.length === 0" class="chart-empty">
      <p>No stance data available.</p>
    </div>
    <Line v-else :data="chartData" :options="chartOptions" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale, Filler } from 'chart.js'

ChartJS.register(Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale, Filler)

const stanceMap = { supportive: 1, neutral: 0, opposing: -1 }
const colors = ['#FF4500', '#1A936F', '#3B82F6', '#F59E0B', '#8B5CF6', '#EC4899', '#06B6D4', '#84CC16']

const props = defineProps({
  agents: { type: Array, default: () => [] },
  totalRounds: { type: Number, default: 10 },
})

const chartData = computed(() => {
  const labels = Array.from({ length: props.totalRounds }, (_, i) => `R${i + 1}`)
  return {
    labels,
    datasets: props.agents.map((agent, idx) => {
      const points = []
      let stance = stanceMap[agent.initial_stance || 'neutral'] ?? 0
      for (let r = 1; r <= props.totalRounds; r++) {
        const shift = (agent.shifts || []).find(s => s.round === r)
        if (shift) stance = stanceMap[shift.new_stance] ?? stance
        points.push(stance)
      }
      return {
        label: agent.entity_name || agent.agent_id,
        data: points,
        borderColor: colors[idx % colors.length],
        backgroundColor: colors[idx % colors.length] + '20',
        tension: 0.3,
        pointRadius: 2,
        pointHoverRadius: 5,
      }
    }),
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
      min: -1.2, max: 1.2,
      ticks: {
        callback: (v) => v === 1 ? 'Supportive' : v === 0 ? 'Neutral' : v === -1 ? 'Opposing' : '',
        stepSize: 1,
      },
      title: { display: true, text: 'Stance' },
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
