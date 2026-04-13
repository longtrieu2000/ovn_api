"use client";

import { useState, useEffect } from "react";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { TrendingUp, Cpu, HardDrive, Activity } from "lucide-react";

export default function PerformanceMetrics({ apiUrl }) {
  const [latencyData, setLatencyData] = useState([]);
  const [cpuData, setCpuData] = useState([]);
  const [timeRange, setTimeRange] = useState("1h");

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 5000);
    return () => clearInterval(interval);
  }, [apiUrl, timeRange]);

  const fetchMetrics = async () => {
    try {
      const response = await fetch(
        `${apiUrl}/api/metrics/history?range=${timeRange}`,
      );
      if (response.ok) {
        const data = await response.json();
        setLatencyData(data.latency || generateMockLatencyData());
        setCpuData(data.cpu || generateMockCpuData());
      } else {
        setLatencyData(generateMockLatencyData());
        setCpuData(generateMockCpuData());
      }
    } catch (error) {
      console.error("Failed to fetch metrics:", error);
      setLatencyData(generateMockLatencyData());
      setCpuData(generateMockCpuData());
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 tracking-tight">
            Performance Metrics
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Historical performance data and trends
          </p>
        </div>
        <div className="flex gap-2">
          {["15m", "1h", "6h", "24h"].map((range) => (
            <button
              key={range}
              onClick={() => setTimeRange(range)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                timeRange === range
                  ? "bg-blue-600 text-white"
                  : "bg-white border border-gray-200 text-gray-700 hover:bg-gray-50"
              }`}
            >
              {range}
            </button>
          ))}
        </div>
      </div>

      {/* Key Performance Indicators */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <KPICard
          icon={Activity}
          label="Avg E2E Latency"
          value="42ms"
          trend="-5.2%"
          trendPositive={true}
        />
        <KPICard
          icon={TrendingUp}
          label="P95 Latency"
          value="78ms"
          trend="+2.1%"
          trendPositive={false}
        />
        <KPICard
          icon={Cpu}
          label="OVN northd CPU"
          value="23%"
          trend="-1.8%"
          trendPositive={true}
        />
        <KPICard
          icon={HardDrive}
          label="OVSDB Memory"
          value="142MB"
          trend="+0.5%"
          trendPositive={true}
        />
      </div>

      {/* Latency Chart */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-base font-semibold text-gray-900">
              Control Plane Latency
            </h3>
            <p className="text-xs text-gray-500 mt-1">
              End-to-end NB → SB → OpenFlow latency over time
            </p>
          </div>
          <div className="flex gap-4">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-sm bg-blue-600"></div>
              <span className="text-xs text-gray-600">NB → SB</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-sm bg-orange-600"></div>
              <span className="text-xs text-gray-600">SB → OpenFlow</span>
            </div>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={latencyData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
            <XAxis
              dataKey="time"
              stroke="#6B7280"
              style={{ fontSize: "12px" }}
              tick={{ fill: "#6B7280" }}
            />
            <YAxis
              stroke="#6B7280"
              style={{ fontSize: "12px" }}
              tick={{ fill: "#6B7280" }}
              label={{
                value: "Latency (ms)",
                angle: -90,
                position: "insideLeft",
                style: { fontSize: "12px", fill: "#6B7280" },
              }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#FFFFFF",
                border: "1px solid #E5E7EB",
                borderRadius: "8px",
                fontSize: "12px",
              }}
            />
            <Line
              type="monotone"
              dataKey="nb_to_sb"
              stroke="#2563EB"
              strokeWidth={2}
              dot={false}
              name="NB → SB"
            />
            <Line
              type="monotone"
              dataKey="sb_to_of"
              stroke="#EA580C"
              strokeWidth={2}
              dot={false}
              name="SB → OpenFlow"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* CPU Usage Chart */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-base font-semibold text-gray-900">
              OVN Component CPU Usage
            </h3>
            <p className="text-xs text-gray-500 mt-1">
              CPU consumption for northd and ovn-controller
            </p>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={cpuData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
            <XAxis
              dataKey="time"
              stroke="#6B7280"
              style={{ fontSize: "12px" }}
              tick={{ fill: "#6B7280" }}
            />
            <YAxis
              stroke="#6B7280"
              style={{ fontSize: "12px" }}
              tick={{ fill: "#6B7280" }}
              label={{
                value: "CPU %",
                angle: -90,
                position: "insideLeft",
                style: { fontSize: "12px", fill: "#6B7280" },
              }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#FFFFFF",
                border: "1px solid #E5E7EB",
                borderRadius: "8px",
                fontSize: "12px",
              }}
            />
            <Area
              type="monotone"
              dataKey="northd"
              stroke="#2563EB"
              fill="#EFF6FF"
              strokeWidth={2}
              name="northd"
            />
            <Area
              type="monotone"
              dataKey="controller"
              stroke="#10B981"
              fill="#D1FAE5"
              strokeWidth={2}
              name="controller"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Performance Breakdown */}
      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4">
            Latency Percentiles
          </h3>
          <div className="space-y-3">
            <PercentileBar label="P50" value={42} max={100} color="blue" />
            <PercentileBar label="P75" value={58} max={100} color="blue" />
            <PercentileBar label="P95" value={78} max={100} color="orange" />
            <PercentileBar label="P99" value={92} max={100} color="orange" />
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4">
            Resource Utilization
          </h3>
          <div className="space-y-4">
            <ResourceMetric label="OVSDB NB" metric="142 MB" utilization={45} />
            <ResourceMetric label="OVSDB SB" metric="198 MB" utilization={62} />
            <ResourceMetric
              label="OVS Datapath"
              metric="1.2k flows"
              utilization={28}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function KPICard({ icon: Icon, label, value, trend, trendPositive }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <Icon size={20} className="text-blue-600" />
        <span
          className={`text-xs font-medium ${trendPositive ? "text-green-600" : "text-orange-600"}`}
        >
          {trend}
        </span>
      </div>
      <div className="text-2xl font-semibold text-gray-900 tracking-tight">
        {value}
      </div>
      <div className="text-xs text-gray-500 mt-1">{label}</div>
    </div>
  );
}

function PercentileBar({ label, value, max, color }) {
  const percentage = (value / max) * 100;
  const bgColor = color === "blue" ? "bg-blue-600" : "bg-orange-600";

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-gray-700">{label}</span>
        <span className="text-xs text-gray-600">{value}ms</span>
      </div>
      <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full ${bgColor} transition-all duration-300`}
          style={{ width: `${percentage}%` }}
        ></div>
      </div>
    </div>
  );
}

function ResourceMetric({ label, metric, utilization }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-900">{label}</span>
        <span className="text-xs font-medium text-gray-600">{metric}</span>
      </div>
      <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-blue-600 transition-all duration-300"
          style={{ width: `${utilization}%` }}
        ></div>
      </div>
    </div>
  );
}

// Mock data generators
function generateMockLatencyData() {
  const data = [];
  const now = Date.now();
  for (let i = 20; i >= 0; i--) {
    data.push({
      time: new Date(now - i * 3 * 60 * 1000).toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
      }),
      nb_to_sb: 20 + Math.random() * 15,
      sb_to_of: 15 + Math.random() * 12,
    });
  }
  return data;
}

function generateMockCpuData() {
  const data = [];
  const now = Date.now();
  for (let i = 20; i >= 0; i--) {
    data.push({
      time: new Date(now - i * 3 * 60 * 1000).toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
      }),
      northd: 15 + Math.random() * 15,
      controller: 10 + Math.random() * 20,
    });
  }
  return data;
}
