"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Activity,
  Database,
  Network,
  Zap,
  Clock,
  CheckCircle2,
  AlertCircle,
  TrendingUp,
} from "lucide-react";
import CanaryProbeMonitor from "@/components/CanaryProbeMonitor";
import DatabaseStateView from "@/components/DatabaseStateView";
import PerformanceMetrics from "@/components/PerformanceMetrics";
import OpenFlowMonitor from "@/components/OpenFlowMonitor";

export default function OVNDashboard() {
  const [activeTab, setActiveTab] = useState("overview");
  const [healthStatus, setHealthStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [apiUrl, setApiUrl] = useState("http://localhost:8001");

  useEffect(() => {
    fetchHealthStatus();
    const interval = setInterval(fetchHealthStatus, 10000);
    return () => clearInterval(interval);
  }, [apiUrl]);

  const fetchHealthStatus = useCallback(async () => {
    try {
      const response = await fetch(`${apiUrl}/health`);
      if (!response.ok) {
        throw new Error("API not reachable");
      }
      const data = await response.json();
      setHealthStatus(data);
      setLoading(false);
    } catch (error) {
      console.error("Health check failed:", error);
      setHealthStatus({ status: "error", message: error.message });
      setLoading(false);
    }
  }, [apiUrl]);

  const tabs = [
    { id: "overview", label: "Overview", icon: Activity },
    { id: "canary", label: "Canary Probes", icon: Zap },
    { id: "database", label: "Database State", icon: Database },
    { id: "flows", label: "OpenFlow", icon: Network },
    { id: "performance", label: "Performance", icon: TrendingUp },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-[1400px] mx-auto px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
                OVN Control Plane Monitor
              </h1>
              <p className="text-sm text-gray-500 mt-1">
                Real-time SDN infrastructure monitoring and analysis
              </p>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 bg-white border border-gray-200 rounded-full px-3 py-1.5">
                {healthStatus?.status === "healthy" ||
                healthStatus?.status === "ok" ? (
                  <>
                    <div className="w-1.5 h-1.5 bg-green-500 rounded-full"></div>
                    <span className="text-xs font-medium text-gray-700">
                      Healthy
                    </span>
                  </>
                ) : (
                  <>
                    <div className="w-1.5 h-1.5 bg-orange-500 rounded-full"></div>
                    <span className="text-xs font-medium text-gray-700">
                      Degraded
                    </span>
                  </>
                )}
              </div>
              <input
                type="text"
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                placeholder="API URL"
                className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
              />
            </div>
          </div>
        </div>
      </header>

      {/* Tab Navigation */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="flex gap-8">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 pb-3 border-b-2 -mb-[1px] transition-colors ${
                    activeTab === tab.id
                      ? "border-blue-600 text-gray-900 font-medium"
                      : "border-transparent text-gray-500 hover:text-gray-700"
                  }`}
                >
                  <Icon size={16} />
                  <span className="text-sm">{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="max-w-[1400px] mx-auto px-8 py-8">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="text-center">
              <div className="inline-block w-8 h-8 border-2 border-gray-200 border-t-blue-600 rounded-full animate-spin"></div>
              <p className="text-sm text-gray-500 mt-4">
                Connecting to OVN API...
              </p>
            </div>
          </div>
        ) : (
          <>
            {activeTab === "overview" && (
              <OverviewTab apiUrl={apiUrl} healthStatus={healthStatus} />
            )}
            {activeTab === "canary" && <CanaryProbeMonitor apiUrl={apiUrl} />}
            {activeTab === "database" && <DatabaseStateView apiUrl={apiUrl} />}
            {activeTab === "flows" && <OpenFlowMonitor apiUrl={apiUrl} />}
            {activeTab === "performance" && (
              <PerformanceMetrics apiUrl={apiUrl} />
            )}
          </>
        )}
      </main>
    </div>
  );
}

function OverviewTab({ apiUrl, healthStatus }) {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, [apiUrl]);

  const fetchStats = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/stats`);
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (error) {
      console.error("Failed to fetch stats:", error);
    }
  };

  return (
    <div className="space-y-6">
      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard
          title="Control Plane Latency"
          value={stats?.control_plane_latency || "45ms"}
          trend="+2.3%"
          icon={Clock}
          status="good"
        />
        <MetricCard
          title="Active Canary Probes"
          value={stats?.active_probes || "12"}
          trend="stable"
          icon={Zap}
          status="good"
        />
        <MetricCard
          title="OVN Database Connections"
          value={stats?.db_connections || "2"}
          trend="NB + SB"
          icon={Database}
          status="good"
        />
        <MetricCard
          title="OpenFlow Rules"
          value={stats?.flow_count || "1,247"}
          trend="+15 today"
          icon={Network}
          status="good"
        />
      </div>

      {/* System Health */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          System Health
        </h2>
        <div className="space-y-3">
          <HealthItem
            label="OVN Northbound DB"
            status="healthy"
            detail="Connected via OVSDB IDL"
          />
          <HealthItem
            label="OVN Southbound DB"
            status="healthy"
            detail="Connected via OVSDB IDL"
          />
          <HealthItem
            label="OVS DataPath"
            status="healthy"
            detail="Flow dump operational"
          />
          <HealthItem
            label="Canary Pipeline"
            status="healthy"
            detail="All probes responding"
          />
        </div>
      </div>

      {/* Recent Activity */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Recent Events
        </h2>
        <div className="space-y-2">
          <ActivityItem
            time="2m ago"
            event="Canary probe completed"
            detail="Latency: 42ms"
          />
          <ActivityItem
            time="5m ago"
            event="New Logical Switch detected"
            detail="LS-tenant-001"
          />
          <ActivityItem
            time="8m ago"
            event="Flow synchronization"
            detail="1,247 flows active"
          />
          <ActivityItem
            time="12m ago"
            event="Schema refresh"
            detail="NB/SB schema validated"
          />
        </div>
      </div>
    </div>
  );
}

function MetricCard({ title, value, trend, icon: Icon, status }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      <div className="flex items-start justify-between mb-3">
        <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
          <Icon size={20} className="text-blue-600" />
        </div>
        <span className="inline-flex items-center gap-1.5 bg-white border border-gray-200 rounded-full px-2 py-0.5 text-xs text-gray-700">
          {trend}
        </span>
      </div>
      <div className="text-2xl font-semibold text-gray-900 tracking-tight">
        {value}
      </div>
      <div className="text-sm text-gray-500 mt-1">{title}</div>
    </div>
  );
}

function HealthItem({ label, status, detail }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
      <div className="flex items-center gap-3">
        {status === "healthy" ? (
          <CheckCircle2 size={18} className="text-green-500" />
        ) : (
          <AlertCircle size={18} className="text-orange-500" />
        )}
        <div>
          <div className="text-sm font-medium text-gray-900">{label}</div>
          <div className="text-xs text-gray-500">{detail}</div>
        </div>
      </div>
      <span className="inline-flex items-center gap-1.5 bg-white border border-gray-200 rounded-full px-3 py-1 text-xs text-gray-700">
        <div
          className={`w-1.5 h-1.5 rounded-full ${status === "healthy" ? "bg-green-500" : "bg-orange-500"}`}
        ></div>
        {status}
      </span>
    </div>
  );
}

function ActivityItem({ time, event, detail }) {
  return (
    <div className="flex items-start gap-3 py-2">
      <span className="text-gray-400 mr-2 text-xs font-medium mt-0.5">-</span>
      <div className="flex-1">
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-900">{event}</span>
          <span className="text-xs text-gray-500">{time}</span>
        </div>
        <div className="text-xs text-gray-500 mt-0.5">{detail}</div>
      </div>
    </div>
  );
}
