"use client";

import { useState, useEffect } from "react";
import { Database, RefreshCw, Search } from "lucide-react";

export default function DatabaseStateView({ apiUrl }) {
  const [activeDb, setActiveDb] = useState("northbound");
  const [tables, setTables] = useState([]);
  const [selectedTable, setSelectedTable] = useState(null);
  const [tableData, setTableData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    fetchTables();
  }, [apiUrl, activeDb]);

  const fetchTables = async () => {
    setLoading(true);
    try {
      const endpoint =
        activeDb === "northbound" ? "/api/ovn/nb/tables" : "/api/ovn/sb/tables";
      const response = await fetch(`${apiUrl}${endpoint}`);
      if (response.ok) {
        const data = await response.json();
        setTables(data.tables || []);
      }
      setLoading(false);
    } catch (error) {
      console.error("Failed to fetch tables:", error);
      setLoading(false);
    }
  };

  const fetchTableData = async (tableName) => {
    try {
      const endpoint =
        activeDb === "northbound"
          ? `/api/ovn/nb/table/${tableName}`
          : `/api/ovn/sb/table/${tableName}`;
      const response = await fetch(`${apiUrl}${endpoint}`);
      if (response.ok) {
        const data = await response.json();
        setTableData(data);
        setSelectedTable(tableName);
      }
    } catch (error) {
      console.error("Failed to fetch table data:", error);
    }
  };

  const filteredTables = tables.filter((table) =>
    table.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 tracking-tight">
            OVSDB State Explorer
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Browse OVN Northbound and Southbound database tables
          </p>
        </div>
        <button
          onClick={fetchTables}
          className="inline-flex items-center gap-2 bg-white border border-gray-200 rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {/* Database Selector */}
      <div className="flex gap-2">
        <button
          onClick={() => setActiveDb("northbound")}
          className={`flex-1 py-3 px-4 rounded-lg border-2 transition-all text-sm font-medium ${
            activeDb === "northbound"
              ? "border-blue-600 bg-blue-50 text-blue-600"
              : "border-gray-200 bg-white text-gray-600 hover:border-gray-300"
          }`}
        >
          <div className="flex items-center justify-center gap-2">
            <Database size={18} />
            Northbound DB
          </div>
          <div className="text-xs text-gray-500 mt-1">High-level intent</div>
        </button>
        <button
          onClick={() => setActiveDb("southbound")}
          className={`flex-1 py-3 px-4 rounded-lg border-2 transition-all text-sm font-medium ${
            activeDb === "southbound"
              ? "border-blue-600 bg-blue-50 text-blue-600"
              : "border-gray-200 bg-white text-gray-600 hover:border-gray-300"
          }`}
        >
          <div className="flex items-center justify-center gap-2">
            <Database size={18} />
            Southbound DB
          </div>
          <div className="text-xs text-gray-500 mt-1">Physical bindings</div>
        </button>
      </div>

      <div className="grid grid-cols-12 gap-6">
        {/* Tables List */}
        <div className="col-span-4 bg-white rounded-xl border border-gray-200 p-6">
          <div className="mb-4">
            <div className="relative">
              <Search
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
              />
              <input
                type="text"
                placeholder="Search tables..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
              />
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="inline-block w-6 h-6 border-2 border-gray-200 border-t-blue-600 rounded-full animate-spin"></div>
            </div>
          ) : (
            <div className="space-y-1 max-h-[600px] overflow-y-auto">
              {filteredTables.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-8">
                  No tables found
                </p>
              ) : (
                filteredTables.map((table) => (
                  <button
                    key={table}
                    onClick={() => fetchTableData(table)}
                    className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                      selectedTable === table
                        ? "bg-blue-50 text-blue-600 font-medium"
                        : "text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    {table}
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Table Content */}
        <div className="col-span-8 bg-white rounded-xl border border-gray-200 p-6">
          {!selectedTable ? (
            <div className="flex flex-col items-center justify-center py-20">
              <Database size={48} className="text-gray-300 mb-3" />
              <p className="text-sm text-gray-500">
                Select a table to view its contents
              </p>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-base font-semibold text-gray-900">
                  {selectedTable}
                </h3>
                <span className="inline-flex items-center gap-1.5 bg-white border border-gray-200 rounded-full px-3 py-1 text-xs text-gray-700">
                  {tableData?.rows?.length || 0} rows
                </span>
              </div>

              {tableData?.rows?.length === 0 ? (
                <div className="text-center py-12">
                  <p className="text-sm text-gray-500">No data in this table</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-gray-200">
                        <th className="text-left text-xs font-medium text-gray-500 pb-3 pr-4">
                          UUID
                        </th>
                        <th className="text-left text-xs font-medium text-gray-500 pb-3 pr-4">
                          Name
                        </th>
                        <th className="text-left text-xs font-medium text-gray-500 pb-3">
                          Attributes
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {(tableData?.rows || mockTableData).map((row, index) => (
                        <tr
                          key={index}
                          className="border-b border-gray-100 last:border-0"
                        >
                          <td className="py-3 pr-4 text-xs font-mono text-gray-600">
                            {row.uuid}
                          </td>
                          <td className="py-3 pr-4 text-sm text-gray-900">
                            {row.name}
                          </td>
                          <td className="py-3">
                            <div className="flex flex-wrap gap-1">
                              {row.attributes.map((attr, i) => (
                                <span
                                  key={i}
                                  className="inline-flex items-center bg-white border border-gray-200 rounded-full px-2 py-0.5 text-xs text-gray-700"
                                >
                                  {attr}
                                </span>
                              ))}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Mock data for demonstration when API is not available
const mockTableData = [
  {
    uuid: "a1b2c3d4-e5f6-7890",
    name: "LS-tenant-001",
    attributes: ["ports: 4", "acls: 2", "qos_rules: 0"],
  },
  {
    uuid: "b2c3d4e5-f6a7-8901",
    name: "LS-tenant-002",
    attributes: ["ports: 8", "acls: 5", "qos_rules: 1"],
  },
  {
    uuid: "c3d4e5f6-a7b8-9012",
    name: "LS-provider-net",
    attributes: ["ports: 2", "acls: 0", "qos_rules: 0"],
  },
];
