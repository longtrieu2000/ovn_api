"use client";

import { useState, useEffect } from "react";
import { Zap, Clock, CheckCircle2, XCircle, Activity } from "lucide-react";

export default function CanaryProbeMonitor({ apiUrl }) {
  const [probes, setProbes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [latestTrace, setLatestTrace] = useState(null);

  useEffect(() => {
    fetchProbes();
    fetchLatestTrace();
    const interval = setInterval(() => {
      fetchProbes();
      fetchLatestTrace();
    }, 3000);
    return () => clearInterval(interval);
  }, [apiUrl]);

  const fetchProbes = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/traces/canary/runs?limit=20`);
      if (response.ok) {
        const data = await response.json();
        setProbes(Array.isArray(data) ? data : []);
      }
      setLoading(false);
    } catch (error) {
      console.error("Failed to fetch probes:", error);
      setLoading(false);
    }
  };

  const fetchLatestTrace = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/traces/canary/runs?limit=1`);
      if (response.ok) {
        const data = await response.json();
        if (Array.isArray(data) && data.length > 0) {
          const detailResponse = await fetch(
            `${apiUrl}/api/v1/traces/canary/runs/${data[0].probe_id}`,
          );
          if (detailResponse.ok) {
            setLatestTrace(await detailResponse.json());
          }
        } else {
          setLatestTrace(null);
        }
      }
    } catch (error) {
      console.error("Failed to fetch latest trace:", error);
    }
  };

  const triggerProbe = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/traces/canary/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resource_type: "logical_switch",
          timeout_s: 15,
          poll_interval_ms: 250,
          bridge: "br-int",
        }),
      });
      if (response.ok) {
        fetchProbes();
        fetchLatestTrace();
      }
    } catch (error) {
      console.error("Failed to trigger probe:", error);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="inline-block w-8 h-8 border-2 border-gray-200 border-t-blue-600 rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Actions */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 tracking-tight">
            Canary Probe Monitoring
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            End-to-end latency measurement for OVN control plane
          </p>
        </div>
        <button
          onClick={triggerProbe}
          className="inline-flex items-center gap-2 bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
        >
          <Zap size={16} />
          Trigger Probe
        </button>
      </div>

      {/* Latest Trace Summary */}
      {latestTrace && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h3 className="text-base font-semibold text-gray-900">
                Latest Trace Results
              </h3>
              <p className="text-xs text-gray-500 mt-1">
                Probe ID: {latestTrace?.probe_id || "N/A"}
              </p>
            </div>
            <span className="inline-flex items-center gap-1.5 bg-white border border-gray-200 rounded-full px-3 py-1 text-xs text-gray-700">
              <div className="w-1.5 h-1.5 bg-green-500 rounded-full"></div>
              Completed
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <LatencyMetric
              label="NB → SB Latency"
              value={formatLatency(latestTrace?.result?.nb_to_sb_latency_ms)}
              sublabel="northd compilation"
            />
            <LatencyMetric
              label="SB → OpenFlow Latency"
              value={formatLatency(latestTrace?.result?.sb_to_openflow_latency_ms)}
              sublabel="controller realization"
            />
            <LatencyMetric
              label="Total E2E Latency"
              value={formatLatency(latestTrace?.result?.total_latency_ms)}
              sublabel="intent to datapath"
            />
          </div>
        </div>
      )}

      {/* Active Probes List */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-base font-semibold text-gray-900 mb-4">
          Active Probes
        </h3>

        {probes.length === 0 ? (
          <div className="text-center py-12">
            <Zap size={48} className="mx-auto text-gray-300 mb-3" />
            <p className="text-sm text-gray-500">No active probes</p>
            <p className="text-xs text-gray-400 mt-1">
              Trigger a probe to start monitoring
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {probes.map((probe, index) => (
              <ProbeItem key={index} probe={probe} />
            ))}
          </div>
        )}
      </div>

      {/* Pipeline Visualization */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-base font-semibold text-gray-900 mb-4">
          Trace Pipeline
        </h3>
        <div className="flex items-center gap-4">
          <PipelineStep
            label="NB Write"
            sublabel="Logical Switch creation"
            status="complete"
          />
          <PipelineArrow />
          <PipelineStep
            label="northd"
            sublabel="NB → SB compilation"
            status="complete"
          />
          <PipelineArrow />
          <PipelineStep
            label="ovn-controller"
            sublabel="SB → OpenFlow"
            status="complete"
          />
          <PipelineArrow />
          <PipelineStep
            label="OVS DataPath"
            sublabel="Flow installation"
            status="complete"
          />
        </div>
      </div>
    </div>
  );
}

function LatencyMetric({ label, value, sublabel }) {
  return (
    <div className="border border-gray-200 rounded-lg p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-2xl font-semibold text-gray-900 tracking-tight">
        {value}
      </div>
      <div className="text-xs text-gray-400 mt-1">{sublabel}</div>
    </div>
  );
}

function ProbeItem({ probe }) {
  const updatedAt = probe.updated_at || probe.started_at || probe.queued_at;
  return (
    <div className="flex items-center justify-between py-3 border-b border-gray-100 last:border-0">
      <div className="flex items-center gap-3">
        <Activity size={16} className="text-blue-600" />
        <div>
          <div className="text-sm font-medium text-gray-900">
            {probe.resource_name || "Canary Probe"}
          </div>
          <div className="text-xs text-gray-500">
            ID: {probe.probe_id || "unknown"}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xs text-gray-500">
          {updatedAt ? new Date(updatedAt).toLocaleString() : "Just now"}
        </span>
        <span className="inline-flex items-center gap-1.5 bg-blue-50 text-blue-600 rounded-full px-3 py-1 text-xs font-medium">
          <Clock size={12} />
          {probe.status || "queued"}
        </span>
      </div>
    </div>
  );
}

function PipelineStep({ label, sublabel, status }) {
  return (
    <div className="flex-1 text-center">
      <div
        className={`w-12 h-12 mx-auto rounded-lg flex items-center justify-center mb-2 ${
          status === "complete" ? "bg-green-50" : "bg-gray-50"
        }`}
      >
        {status === "complete" ? (
          <CheckCircle2 size={24} className="text-green-600" />
        ) : (
          <XCircle size={24} className="text-gray-400" />
        )}
      </div>
      <div className="text-xs font-medium text-gray-900">{label}</div>
      <div className="text-xs text-gray-500 mt-0.5">{sublabel}</div>
    </div>
  );
}

function PipelineArrow() {
  return (
    <div className="flex-shrink-0">
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        className="text-gray-300"
      >
        <path
          d="M5 12h14m0 0l-6-6m6 6l-6 6"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

function formatLatency(value) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return `${Math.round(value)}ms`;
}
