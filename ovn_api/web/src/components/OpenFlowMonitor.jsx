"use client";

import { useState, useEffect } from "react";
import { Network, Filter, Download } from "lucide-react";

export default function OpenFlowMonitor({ apiUrl }) {
  const [flows, setFlows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterTable, setFilterTable] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    fetchFlows();
    const interval = setInterval(fetchFlows, 5000);
    return () => clearInterval(interval);
  }, [apiUrl]);

  const fetchFlows = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/ovs/flows`);
      if (response.ok) {
        const data = await response.json();
        setFlows(data.flows || mockFlows);
      }
      setLoading(false);
    } catch (error) {
      console.error("Failed to fetch flows:", error);
      setFlows(mockFlows);
      setLoading(false);
    }
  };

  const downloadFlows = () => {
    const dataStr = JSON.stringify(flows, null, 2);
    const dataBlob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `openflow-dump-${Date.now()}.json`;
    link.click();
  };

  const filteredFlows = flows.filter((flow) => {
    const matchesTable = filterTable === "all" || flow.table === filterTable;
    const matchesSearch =
      flow.match.toLowerCase().includes(searchQuery.toLowerCase()) ||
      flow.actions.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesTable && matchesSearch;
  });

  const uniqueTables = ["all", ...new Set(flows.map((f) => f.table))];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 tracking-tight">
            OpenFlow Monitor
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Real-time OpenFlow rule inspection and analysis
          </p>
        </div>
        <button
          onClick={downloadFlows}
          className="inline-flex items-center gap-2 bg-white border border-gray-200 rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
        >
          <Download size={16} />
          Export Flows
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard label="Total Flows" value={flows.length.toLocaleString()} />
        <StatCard label="Active Tables" value={uniqueTables.length - 1} />
        <StatCard
          label="Cookie Count"
          value={new Set(flows.map((f) => f.cookie)).size}
        />
        <StatCard
          label="Avg Priority"
          value={
            Math.round(
              flows.reduce((acc, f) => acc + f.priority, 0) / flows.length,
            ) || 0
          }
        />
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Filter size={16} className="text-gray-500" />
            <span className="text-sm font-medium text-gray-700">Filter:</span>
          </div>
          <div className="flex gap-2 flex-wrap">
            {uniqueTables.map((table) => (
              <button
                key={table}
                onClick={() => setFilterTable(table)}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                  filterTable === table
                    ? "bg-blue-600 text-white"
                    : "bg-white border border-gray-200 text-gray-700 hover:bg-gray-50"
                }`}
              >
                {table === "all" ? "All Tables" : `Table ${table}`}
              </button>
            ))}
          </div>
          <input
            type="text"
            placeholder="Search flows..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="ml-auto px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
          />
        </div>
      </div>

      {/* Flows Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="inline-block w-8 h-8 border-2 border-gray-200 border-t-blue-600 rounded-full animate-spin"></div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left text-xs font-medium text-gray-500 px-6 py-3">
                    Table
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 px-6 py-3">
                    Priority
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 px-6 py-3">
                    Cookie
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 px-6 py-3">
                    Match
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 px-6 py-3">
                    Actions
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 px-6 py-3">
                    Packets
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredFlows.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-center py-12">
                      <Network
                        size={48}
                        className="mx-auto text-gray-300 mb-3"
                      />
                      <p className="text-sm text-gray-500">
                        No flows match your filters
                      </p>
                    </td>
                  </tr>
                ) : (
                  filteredFlows.map((flow, index) => (
                    <tr
                      key={index}
                      className="border-b border-gray-100 hover:bg-gray-50 transition-colors"
                    >
                      <td className="px-6 py-4 text-sm font-medium text-gray-900">
                        {flow.table}
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-flex items-center bg-white border border-gray-200 rounded-full px-2 py-0.5 text-xs text-gray-700">
                          {flow.priority}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-xs font-mono text-gray-600">
                        {flow.cookie}
                      </td>
                      <td className="px-6 py-4 text-xs font-mono text-gray-900 max-w-xs truncate">
                        {flow.match}
                      </td>
                      <td className="px-6 py-4 text-xs font-mono text-blue-600 max-w-xs truncate">
                        {flow.actions}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-600">
                        {flow.packets.toLocaleString()}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Flow Stats */}
      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-3">
            Top Actions
          </h3>
          <div className="space-y-2">
            <ActionStat action="output:LOCAL" count={342} />
            <ActionStat action="resubmit" count={289} />
            <ActionStat action="drop" count={156} />
            <ActionStat action="mod_dl_dst" count={94} />
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-3">
            Priority Distribution
          </h3>
          <div className="space-y-2">
            <PriorityStat range="0-100" count={523} />
            <PriorityStat range="100-1000" count={412} />
            <PriorityStat range="1000-10000" count={298} />
            <PriorityStat range="10000+" count={14} />
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-2xl font-semibold text-gray-900 tracking-tight">
        {value}
      </div>
    </div>
  );
}

function ActionStat({ action, count }) {
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-sm font-mono text-gray-700">{action}</span>
      <span className="inline-flex items-center bg-white border border-gray-200 rounded-full px-2 py-0.5 text-xs text-gray-700">
        {count}
      </span>
    </div>
  );
}

function PriorityStat({ range, count }) {
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-sm text-gray-700">{range}</span>
      <span className="inline-flex items-center bg-white border border-gray-200 rounded-full px-2 py-0.5 text-xs text-gray-700">
        {count} flows
      </span>
    </div>
  );
}

// Mock data for demonstration
const mockFlows = [
  {
    table: 0,
    priority: 100,
    cookie: "0xa1b2c3d4",
    match: "in_port=1,dl_type=0x0800",
    actions: "resubmit(,1)",
    packets: 1247,
  },
  {
    table: 0,
    priority: 90,
    cookie: "0xa1b2c3d4",
    match: "in_port=2,dl_src=fa:16:3e:*",
    actions: "output:LOCAL",
    packets: 8932,
  },
  {
    table: 1,
    priority: 200,
    cookie: "0xb2c3d4e5",
    match: "ip,nw_dst=10.0.0.0/24",
    actions: "mod_dl_dst:fa:16:3e:01:02:03,output:3",
    packets: 5421,
  },
  {
    table: 1,
    priority: 150,
    cookie: "0xb2c3d4e5",
    match: "tcp,tp_dst=80",
    actions: "resubmit(,2)",
    packets: 3156,
  },
  {
    table: 2,
    priority: 100,
    cookie: "0xc3d4e5f6",
    match: "arp",
    actions: "NORMAL",
    packets: 892,
  },
  {
    table: 2,
    priority: 50,
    cookie: "0xc3d4e5f6",
    match: "icmp",
    actions: "drop",
    packets: 234,
  },
];
