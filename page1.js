import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  dispatchAdminDeliveryOrder,
  reopenAdminDeliveryLoading,
  saveAdminDeliveryVehicle,
  updateAdminDeliveryVehicleStatus,
} from "../api/adminApi";


const START = Date.now();
const ago = minutes => new Date(START - minutes * 60000).toISOString();
const tomorrow = new Date(START + 24 * 60 * 60000).toISOString().slice(0, 10);

const ORDER = {
  deliveryId: "SD-260805-014",
  requestId: "SR-260805-012",
  status: "LOADING",
  buyer: { name: "Sri Venkateshwara Infra", id: "BYR-260104-028", phone: "+91 98765 43210" },
  address: "Site 4, Industrial Layout, Hoskote, Bengaluru, Karnataka",
  transporter: "Agrawal Transport",
  confirmedAt: ago(180),
  loadingDate: tomorrow,
  dispatchedAt: null,
  deliveredAt: null,
  materials: [
    { id: "40mm", name: "40mm Crushed Stone", quantity: 30, seller: "Vineeth Plant", sellerPhone: "+91 98451 24480", referenceId: "REF-40-024", imageUploadedAt: ago(720), finalRate: 1533.33, colors: ["#697786", "#aeb9c2"] },
    { id: "20mm", name: "20mm Crushed Stone", quantity: 20, seller: "StoneHub Supplies", sellerPhone: "+91 97123 45678", referenceId: "REF-20-038", imageUploadedAt: ago(930), finalRate: 1400, colors: ["#756b62", "#b8ada3"] }
  ]
};

const INITIAL_VEHICLES = [
  { id: "VH-01", number: "KA 01 AB 4582", driver: "Ramesh Kumar", phone: "+91 98760 11242", materialId: "40mm", expectedQty: 16, loadedQty: 16, status: "LOADED", loadedAt: ago(45) },
  { id: "VH-02", number: "KA 53 MX 2198", driver: "Suresh N", phone: "+91 98450 77331", materialId: "40mm", expectedQty: 14, loadedQty: 14, status: "LOADED", loadedAt: ago(25) },
  { id: "VH-03", number: "", driver: "", phone: "", materialId: "20mm", expectedQty: 16, loadedQty: 0, status: "PENDING", loadedAt: null },
  { id: "VH-04", number: "", driver: "", phone: "", materialId: "20mm", expectedQty: 4, loadedQty: 0, status: "PENDING", loadedAt: null }
];

function Icon({ name, size = 18 }) {
  const c = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };
  const p = {
    back: <><path d="m15 18-6-6 6-6"/><path d="M9 12h10"/></>, refresh: <><path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 9a7 7 0 0 1 12-2l2 2M4 15l2 2a7 7 0 0 0 12-2"/></>,
    cube: <><path d="m12 2 8 4.5v9L12 20l-8-4.5v-9L12 2Z"/><path d="m4 6.5 8 4.5 8-4.5M12 11v9"/></>, clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    user: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>, phone: <path d="M22 16.9v3a2 2 0 0 1-2.2 2A19.8 19.8 0 0 1 3.1 5.2 2 2 0 0 1 5.1 3h3a2 2 0 0 1 2 1.7c.2 1 .4 2 .8 2.8a2 2 0 0 1-.5 2.1l-1.2 1.2a16 16 0 0 0 4.1 4.1l1.2-1.2a2 2 0 0 1 2.1-.5c.9.4 1.8.6 2.8.8a2 2 0 0 1 1.7 1.6Z"/>,
    copy: <><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></>, pin: <><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2"/></>,
    truck: <><path d="M3 6h11v10H3zM14 10h4l3 3v3h-7z"/><circle cx="7" cy="18" r="2"/><circle cx="18" cy="18" r="2"/></>, right: <path d="m9 18 6-6-6-6"/>, down: <path d="m6 9 6 6 6-6"/>, check: <path d="m5 12 4 4L19 6"/>,
    lock: <><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></>, edit: <><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/></>, plus: <><path d="M12 5v14M5 12h14"/></>,
    alert: <><path d="M12 3 3 20h18L12 3Z"/><path d="M12 9v4M12 17h.01"/></>, close: <path d="m7 7 10 10M17 7 7 17"/>, route: <><path d="M5 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM19 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"/><path d="M7 17h3a4 4 0 0 0 4-4V9h3"/></>, history: <><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/></>
  };
  return <svg {...c}>{p[name] || p.cube}</svg>;
}

const money = value => `₹${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(Number(value || 0))}`;

function relative(iso, now) {
  if (!iso) return "--";
  const mins = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60000));
  return mins < 60 ? `${mins} min ago` : `${Math.floor(mins / 60)}h ${mins % 60}m ago`;
}

function MaterialArt({ material }) {
  return (
    <div
      className="od-art"
      style={{
        background: `radial-gradient(circle at 28% 30%,${material.colors[1]},transparent 13%),radial-gradient(circle at 70% 68%,${material.colors[1]},transparent 12%),linear-gradient(135deg,${material.colors[0]},${material.colors[1]})`
      }}
    >
      <i/><b/><u/>
    </div>
  );
}

export default function AdminActiveOrderDetails({
  selectedOrder,
  onBack,
  onUpdated,
}) {
  const ORDER = {
    deliveryId:
      selectedOrder?.deliveryId || "",
  
    requestId:
      selectedOrder?.requestId || "",
  
    status:
      selectedOrder?.status || "NEW",
  
    buyer: {
      name:
        selectedOrder?.buyer || "Buyer",
      id: "",
      phone: "",
    },
  
    address:
      selectedOrder?.deliveryArea || "",
  
    transporter:
      selectedOrder?.transporter ||
      "Not assigned",
      transporterPhone:
  selectedOrder?.transporterPhone ||
  selectedOrder?.materials?.find(
    (material) =>
      material.transporterPhone
  )?.transporterPhone ||
  "",
  
    confirmedAt:
      selectedOrder?.confirmedAt ||
      selectedOrder?.updatedAt ||
      new Date().toISOString(),
  
    loadingDate: new Date(
      Date.now() + 24 * 60 * 60 * 1000
    )
      .toISOString()
      .slice(0, 10),
  
    dispatchedAt:
      selectedOrder?.dispatchedAt || null,
  
    deliveredAt:
      selectedOrder?.deliveredAt || null,
  
    materials: Array.isArray(
      selectedOrder?.materials
    )
      ? selectedOrder.materials.map(
          (material, index) => ({
            id:
              material.orderItemId ||
              `material-${index + 1}`,
  
            name:
              material.materialName ||
              "Material",
  
            quantity: Number(
              material.totalTons || 0
            ),
            vehicleBreakdown:
  Array.isArray(
    material.vehicleBreakdown
  )
    ? material.vehicleBreakdown.map(
        (vehicleType) => ({
          id:
            vehicleType.id || "",

          vehicleType:
            vehicleType.vehicleType ||
            "",

          vehicleName:
            vehicleType.vehicleName ||
            vehicleType.vehicleType ||
            "Vehicle",

          capacityTons: Number(
            vehicleType.capacityTons ||
              0
          ),

          quantity: Number(
            vehicleType.quantity || 0
          ),

          totalTons: Number(
            vehicleType.totalTons ||
              0
          ),
        })
      )
    : [],
  
            sourceArea:
  material.sourceArea ||
  "Not recorded",

referenceId:
  material.sampleCode ||
  "Not recorded",

imageUrl:
  material.imageUrl || "",

thumbnailUrl:
  material.thumbnailUrl ||
  material.imageUrl ||
  "",
  
  materialRatePerTon: Number(
    material.materialRatePerTon || 0
  ),
  
  permitRatePerTon:
    material.permitRatePerTon === null ||
    material.permitRatePerTon ===
      undefined ||
    material.permitRatePerTon === ""
      ? null
      : Number(
          material.permitRatePerTon
        ),
  
  transporter:
    material.transporterName ||
    selectedOrder?.transporter ||
    "Not assigned",
  
  transporterPhone:
    material.transporterPhone ||
    selectedOrder?.transporterPhone ||
    "",
  
  transportMethod:
    material.transportMethod ||
    "Not recorded",
  
  transportRate: Number(
    material.transportRate || 0
  ),
  
  transportTotal: Number(
    material.transportTotal || 0
  ),
  
  transportPerTon: Number(
    material.transportPerTon || 0
  ),
  
  finalRate: Number(
    material.finalRate ||
      material.finalRatePerTon ||
      0
  ),
  
            colors: [
              "#697786",
              "#aeb9c2",
            ],
          })
        )
      : [],
  };

  const [now, setNow] = useState(Date.now());
  const initialStatus =
  selectedOrder?.status === "NEW"
    ? "CONFIRMED"
    : selectedOrder?.status || "CONFIRMED";

const [openStage, setOpenStage] =
  useState(initialStatus);

const [orderStatus, setOrderStatus] =
  useState(initialStatus);

const [loadingDate, setLoadingDate] =
  useState(
    new Date(Date.now() + 24 * 60 * 60 * 1000)
      .toISOString()
      .slice(0, 10)
  );
  const [vehicles, setVehicles] = useState([]);
  useEffect(() => {
    if (
      !selectedOrder ||
      vehicles.length > 0
    ) {
      return;
    }
  
    const savedVehicles =
      Array.isArray(selectedOrder.vehicles)
        ? selectedOrder.vehicles
        : [];
  
    if (savedVehicles.length > 0) {
      setVehicles(
        savedVehicles.map((vehicle) => ({
          id:
            vehicle.id ||
            `VH-${String(
              vehicle.slotNumber || 1
            ).padStart(2, "0")}`,
  
          persistedId: vehicle.id || "",
  
          number:
            vehicle.vehicleNumber || "",
  
          driver:
            vehicle.driverName || "",
  
          phone:
            vehicle.driverPhone || "",
  
          materialId:
            vehicle.orderItemId || "",
  
          expectedQty: Number(
            vehicle.expectedTons || 0
          ),
  
          loadedQty: Number(
            vehicle.loadedTons || 0
          ),
  
          status: String(
            vehicle.status || "PENDING"
          ).toUpperCase(),
  
          loadedAt:
            vehicle.loadedAt || null,
  
          dispatchedAt:
            vehicle.dispatchedAt || null,
  
          deliveredAt:
            vehicle.deliveredAt || null,
        }))
      );
  
      return;
    }
  
    const vehicleSlots = [];
  
    ORDER.materials.forEach(
      (material, materialIndex) => {
        const materialFromApi =
          selectedOrder.materials?.[
            materialIndex
          ];
  
        const expectedVehicleCount =
          Number(
            materialFromApi?.totalVehicles ||
              0
          );
  
        const vehicleCount =
          expectedVehicleCount > 0
            ? expectedVehicleCount
            : 1;
  
        const quantityPerVehicle =
          material.quantity / vehicleCount;
  
        for (
          let vehicleIndex = 0;
          vehicleIndex < vehicleCount;
          vehicleIndex += 1
        ) {
          const isLastVehicle =
            vehicleIndex ===
            vehicleCount - 1;
  
          const allocatedBefore =
            Math.round(
              quantityPerVehicle *
                vehicleIndex *
                100
            ) / 100;
  
          const expectedQty =
            isLastVehicle
              ? Math.round(
                  (material.quantity -
                    allocatedBefore) *
                    100
                ) / 100
              : Math.round(
                  quantityPerVehicle * 100
                ) / 100;
  
          vehicleSlots.push({
            id: `VH-${String(
              vehicleSlots.length + 1
            ).padStart(2, "0")}`,
  
            persistedId: "",
            number: "",
            driver: "",
            phone: "",
            materialId: material.id,
            expectedQty,
            loadedQty: 0,
            status: "PENDING",
            loadedAt: null,
            dispatchedAt: null,
            deliveredAt: null,
          });
        }
      }
    );
  
    setVehicles(vehicleSlots);
  }, [selectedOrder, vehicles.length]);

  const addAnotherVehicleSlot = () => {
    if (vehicles.length >= 100) {
      notify(
        "A maximum of 100 vehicle slots is allowed."
      );
      return;
    }
  
    const completedStatuses =
      new Set([
        "LOADED",
        "DISPATCHED",
        "DELIVERED",
      ]);
  
    const materialProgress =
      ORDER.materials.map((material) => {
        const loadedQuantity =
          vehicles
            .filter(
              (vehicle) =>
                vehicle.materialId ===
                  material.id &&
                completedStatuses.has(
                  String(
                    vehicle.status || ""
                  ).toUpperCase()
                )
            )
            .reduce(
              (sum, vehicle) =>
                sum +
                Number(
                  vehicle.loadedQty || 0
                ),
              0
            );
  
        const allocatedQuantity =
          vehicles
            .filter(
              (vehicle) =>
                vehicle.materialId ===
                  material.id
            )
            .reduce(
              (sum, vehicle) =>
                sum +
                Number(
                  vehicle.expectedQty || 0
                ),
              0
            );
  
        return {
          material,
          loadedQuantity,
          allocatedQuantity,
  
          remainingToLoad:
            Math.max(
              0,
              Number(
                material.quantity || 0
              ) - loadedQuantity
            ),
  
          remainingToAllocate:
            Math.max(
              0,
              Number(
                material.quantity || 0
              ) - allocatedQuantity
            ),
        };
      });
  
    const incompleteMaterial =
      materialProgress.find(
        (item) =>
          item.remainingToLoad > 0 &&
          item.remainingToAllocate > 0
      ) ||
      materialProgress.find(
        (item) =>
          item.remainingToLoad > 0
      );
  
    if (!incompleteMaterial) {
      notify(
        "All material quantities are already loaded."
      );
      return;
    }
  
    const nextSlotNumber =
      vehicles.length + 1;
  
    const newVehicle = {
      id: `VH-${String(
        nextSlotNumber
      ).padStart(2, "0")}`,
  
      persistedId: "",
      number: "",
      driver: "",
      phone: "",
  
      materialId:
        incompleteMaterial.material.id,
  
      expectedQty:
        incompleteMaterial
          .remainingToAllocate > 0
          ? Math.round(
              incompleteMaterial
                .remainingToAllocate *
                100
            ) / 100
          : "",
  
      loadedQty: 0,
      status: "PENDING",
      loadedAt: null,
      dispatchedAt: null,
      deliveredAt: null,
    };
  
    setVehicles((currentVehicles) => [
      ...currentVehicles,
      newVehicle,
    ]);
  
    setFormErrors({});
    setVehicleForm({
      ...newVehicle,
    });
  };
  
  const [vehicleForm, setVehicleForm] = useState(null);
  const [materialDetail, setMaterialDetail] = useState(null);
  const [
    transporterDetail,
    setTransporterDetail,
  ] = useState(null);
  const [
    materialRateDetail,
    setMaterialRateDetail,
  ] = useState(null);
  const [formErrors, setFormErrors] = useState({});
  const [statusEditor, setStatusEditor] = useState(null);
  const [dispatchConfirm, setDispatchConfirm] = useState(false);
  const [reverseDispatch, setReverseDispatch] = useState(false);
  const [deliveryCorrection, setDeliveryCorrection] = useState(false);
  const [issueModal, setIssueModal] = useState(false);
  const [issue, setIssue] = useState("");
  const [reason, setReason] = useState("");
  const [toast, setToast] = useState("");
  const [activity, setActivity] = useState([
    {
      time: ORDER.confirmedAt,
      text: "Order confirmed",
    },
  ]);
  useEffect(() => {
    const savedActivity = [];
  
    const savedVehicles =
      Array.isArray(selectedOrder?.vehicles)
        ? selectedOrder.vehicles
        : [];

        if (selectedOrder?.deliveredAt) {
          savedActivity.push({
            time: selectedOrder.deliveredAt,
            text: "Delivery confirmed by buyer",
          });
        }
  
    if (selectedOrder?.dispatchedAt) {
      savedActivity.push({
        time: selectedOrder.dispatchedAt,
        text: "All vehicles dispatched",
      });
    }
  
    savedVehicles.forEach((vehicle) => {
      if (vehicle.loadedAt) {
        savedActivity.push({
          time: vehicle.loadedAt,
          text: `Vehicle ${
            vehicle.slotNumber || 1
          } loaded`,
        });
      }
    });
  
    if (selectedOrder?.loadingStartedAt) {
      savedActivity.push({
        time: selectedOrder.loadingStartedAt,
        text: "Loading started",
      });
    }
  
    if (ORDER.confirmedAt) {
      savedActivity.push({
        time: ORDER.confirmedAt,
        text: "Order confirmed",
      });
    }
  
    savedActivity.sort(
      (firstActivity, secondActivity) =>
        new Date(
          secondActivity.time
        ).getTime() -
        new Date(
          firstActivity.time
        ).getTime()
    );
  
    setActivity(savedActivity);
  }, [
    selectedOrder?.deliveryId,
    selectedOrder?.loadingStartedAt,
    selectedOrder?.dispatchedAt,
    selectedOrder?.deliveredAt,
    selectedOrder?.vehicles,
    ORDER.confirmedAt,
  ]);
  const toastTimer = useRef(null);

  useEffect(() => { const id = window.setInterval(() => setNow(Date.now()), 30000); return () => window.clearInterval(id); }, []);
  useEffect(() => () => window.clearTimeout(toastTimer.current), []);
  if (
    !selectedOrder?.deliveryId ||
    !selectedOrder?.requestId
  ) {
    return (
      <div className="od-root">
        <style>{CSS}</style>
  
        <main className="od-width od-main">
          <section className="od-panel">
            <div className="od-head">
              <Icon name="alert" size={15} />
              <b>Unable to Load Order</b>
            </div>
  
            <p>
              The selected delivery order is missing.
            </p>
  
            <button
              className="od-save"
              type="button"
              onClick={() => onBack?.()}
            >
              Back to Active Orders
            </button>
          </section>
        </main>
      </div>
    );
  }
  const notify = text => { setToast(text); window.clearTimeout(toastTimer.current); toastTimer.current = window.setTimeout(() => setToast(""), 2300); };
  const log = text => setActivity(list => [{ time: new Date().toISOString(), text }, ...list]);
  const copy = async (text, label) => { try { await navigator.clipboard.writeText(text); notify(`${label} copied`); } catch { notify(text); } };

  const totals = useMemo(() => {
    const completedVehicleStatuses =
      new Set([
        "LOADED",
        "DISPATCHED",
        "DELIVERED",
      ]);
  
    const loadedQty = vehicles.reduce(
      (sum, vehicle) => {
        const shouldCount =
          completedVehicleStatuses.has(
            String(
              vehicle.status || ""
            ).toUpperCase()
          );
  
        return (
          sum +
          (shouldCount
            ? Number(
                vehicle.loadedQty || 0
              )
            : 0)
        );
      },
      0
    );
  
    const loadedVehicles =
      vehicles.filter((vehicle) =>
        completedVehicleStatuses.has(
          String(
            vehicle.status || ""
          ).toUpperCase()
        )
      ).length;
  
    const byMaterial =
      ORDER.materials.map(
        (material) => {
          const loaded =
            vehicles
              .filter(
                (vehicle) =>
                  vehicle.materialId ===
                    material.id &&
                  completedVehicleStatuses.has(
                    String(
                      vehicle.status || ""
                    ).toUpperCase()
                  )
              )
              .reduce(
                (sum, vehicle) =>
                  sum +
                  Number(
                    vehicle.loadedQty || 0
                  ),
                0
              );
  
          return {
            ...material,
            loaded,
          };
        }
      );
  
    const totalQty =
      ORDER.materials.reduce(
        (sum, material) =>
          sum +
          Number(
            material.quantity || 0
          ),
        0
      );
  
    const orderValue =
      ORDER.materials.reduce(
        (sum, material) =>
          sum +
          Number(
            material.quantity || 0
          ) *
            Number(
              material.finalRate || 0
            ),
        0
      );
  
      const allocatedQty =
      vehicles.reduce(
        (sum, vehicle) =>
          sum +
          Number(
            vehicle.expectedQty || 0
          ),
        0
      );
    
    const remainingToAllocate =
      Math.max(
        0,
        Math.round(
          (
            totalQty -
            allocatedQty
          ) * 100
        ) / 100
      );
    
    return {
      loadedQty,
      loadedVehicles,
      allocatedQty,
      remainingToAllocate,
      byMaterial,
      totalQty,
      orderValue,
    };
  }, [vehicles, ORDER.materials]);
  const transporterRows = useMemo(() => {
    const transporterMap = new Map();
  
    ORDER.materials.forEach((material) => {
      const transporterName =
        String(
          material.transporter ||
            "Not assigned"
        ).trim() || "Not assigned";
  
      const transporterKey =
        transporterName.toLowerCase();
  
      if (
        !transporterMap.has(
          transporterKey
        )
      ) {
        transporterMap.set(
          transporterKey,
          {
            name: transporterName,
  
            phone:
              material.transporterPhone ||
              "",
  
            vehicleTypes: new Map(),
          }
        );
      }
  
      const transporter =
        transporterMap.get(
          transporterKey
        );
  
      if (
        !transporter.phone &&
        material.transporterPhone
      ) {
        transporter.phone =
          material.transporterPhone;
      }
  
      const breakdown =
        Array.isArray(
          material.vehicleBreakdown
        )
          ? material.vehicleBreakdown
          : [];
  
      breakdown.forEach(
        (vehicleType) => {
          const vehicleName =
            String(
              vehicleType.vehicleName ||
                vehicleType.vehicleType ||
                "Vehicle"
            ).trim() || "Vehicle";
  
          const vehicleKey =
            vehicleName.toLowerCase();
  
          const existingType =
            transporter.vehicleTypes.get(
              vehicleKey
            ) || {
              vehicleName,
              capacityTons: Number(
                vehicleType.capacityTons ||
                  0
              ),
              quantity: 0,
              totalTons: 0,
            };
  
          existingType.quantity += Number(
            vehicleType.quantity || 0
          );
  
          existingType.totalTons += Number(
            vehicleType.totalTons || 0
          );
  
          transporter.vehicleTypes.set(
            vehicleKey,
            existingType
          );
        }
      );
    });
  
    return Array.from(
      transporterMap.values()
    ).map((transporter) => {
      const vehicleTypes =
        Array.from(
          transporter.vehicleTypes.values()
        );
  
      const totalVehicles =
        vehicleTypes.reduce(
          (sum, vehicleType) =>
            sum +
            Number(
              vehicleType.quantity || 0
            ),
          0
        );
  
      return {
        name: transporter.name,
        phone: transporter.phone,
        vehicleTypes,
        totalVehicles,
      };
    });
  }, [ORDER.materials]);

  const loadedPct = totals.totalQty > 0 ? Math.min(100, (totals.loadedQty / totals.totalQty) * 100) : 0;
  const allLoaded = totals.loadedQty >= totals.totalQty && vehicles.every(v => v.status === "LOADED");
  const isReadyForDispatch =
  orderStatus === "LOADING" &&
  allLoaded;

const displayStatus =
  isReadyForDispatch
    ? "LOADED"
    : orderStatus;
  const stageRank = { CONFIRMED: 0, LOADING: 1, IN_TRANSIT: 2, DELIVERED: 3 };
  const currentRank =
  orderStatus === "DELIVERED"
    ? 4
    : orderStatus === "IN_TRANSIT"
      ? stageRank.DELIVERED
      : isReadyForDispatch
        ? stageRank.IN_TRANSIT
        : stageRank[orderStatus] ?? 0;

  const saveVehicle = async data => {
  const errors = {};
    const compactNumber = String(data.number || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
    const vehiclePattern = /^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$/;
    const driverPattern = /^[A-Za-z][A-Za-z .'-]*$/;
    const mobile = String(data.phone || "").replace(/\D/g, "");
    const selectedMaterial = ORDER.materials.find(m => m.id === data.materialId);
    const allocatedByOthers = vehicles.filter(v => v.id !== data.id && v.materialId === data.materialId).reduce((sum, v) => sum + Number(v.expectedQty || 0), 0);
    const remaining = Math.max(0, Number(selectedMaterial?.quantity || 0) - allocatedByOthers);
    const expected = Number(data.expectedQty || 0);
    if (!vehiclePattern.test(compactNumber)) errors.number = "Enter a valid number, for example KA 01 AB 4582.";
    if (!driverPattern.test(String(data.driver || "").trim())) errors.driver = "Use letters, spaces, periods, apostrophes, or hyphens only.";
    if (!/^[6-9][0-9]{9}$/.test(mobile)) errors.phone = "Enter a valid 10-digit Indian mobile number.";
    if (!data.materialId) errors.materialId = "Select a material.";
    if (!(expected > 0)) errors.expectedQty = "Expected load must be greater than zero.";
    else if (expected > remaining) errors.expectedQty = `Expected load cannot exceed the remaining ${remaining} t.`;
    const duplicate = vehicles.some(v => v.number && v.number.replace(/[^A-Z0-9]/gi, "").toUpperCase() === compactNumber && v.id !== data.id);
    if (duplicate) errors.number = "This vehicle number is already added.";
    setFormErrors(errors);
    if (Object.keys(errors).length) {
      return;
    }
    
    const slotNumber =
      vehicles.findIndex(
        vehicle => vehicle.id === data.id
      ) + 1;
    
    if (slotNumber < 1) {
      notify("Vehicle slot was not found");
      return;
    }
    
    const formattedNumber = compactNumber.replace(/^([A-Z]{2})([0-9]{1,2})([A-Z]{1,3})([0-9]{4})$/, "$1 $2 $3 $4");
    try {
      const result =
        await saveAdminDeliveryVehicle(
          ORDER.deliveryId,
          slotNumber,
          {
            ...data,
            number: formattedNumber,
            driver: String(
              data.driver
            ).trim(),
            phone: mobile,
            expectedQty: expected,
          }
        );
    
      setVehicles(list =>
        list.map(vehicle =>
          vehicle.id === data.id
            ? {
                ...vehicle,
                ...data,
                number: formattedNumber,
                driver: String(
                  data.driver
                ).trim(),
                phone: mobile,
                expectedQty: expected,
                persistedId:
                  result.vehicle?.id || "",
              }
            : vehicle
        )
      );
    
      setVehicleForm(null);
      setFormErrors({});
    
      notify(
        result.message ||
          "Vehicle details saved"
      );
    } catch (error) {
      console.error(
        "Unable to save vehicle:",
        error
      );
    
      notify(
        error.message ||
          "Unable to save vehicle details."
      );
    }
  };

  const updateVehicleStatus = async () => {
    if (!statusEditor?.vehicle) {
      notify("Vehicle details are missing");
      return;
    }
  
    const slotNumber =
      vehicles.findIndex(
        (vehicle) =>
          vehicle.id ===
          statusEditor.vehicle.id
      ) + 1;
  
    if (slotNumber < 1) {
      notify("Vehicle slot was not found");
      return;
    }
  
    const nextStatus = String(
      statusEditor.status || "PENDING"
    ).toUpperCase();
  
    const loadedQty =
      nextStatus === "LOADED"
        ? Number(
            statusEditor.loadedQty ||
              statusEditor.vehicle.expectedQty ||
              0
          )
        : 0;
  
    try {
      const result =
        await updateAdminDeliveryVehicleStatus(
          ORDER.deliveryId,
          slotNumber,
          {
            status: nextStatus,
            loadedTons: loadedQty,
            reason:
              statusEditor.reason || "",
          }
        );
  
      const updatedVehicle =
        result.vehicle;
  
      setVehicles((list) =>
        list.map((vehicle) =>
          vehicle.id ===
          statusEditor.vehicle.id
            ? {
                ...vehicle,
  
                status: String(
                  updatedVehicle?.status ||
                    nextStatus
                ).toUpperCase(),
  
                loadedQty: Number(
                  updatedVehicle?.loadedTons ||
                    0
                ),
  
                loadedAt:
                  updatedVehicle?.loadedAt ||
                  null,
  
                dispatchedAt:
                  updatedVehicle?.dispatchedAt ||
                  null,
  
                deliveredAt:
                  updatedVehicle?.deliveredAt ||
                  null,
              }
            : vehicle
        )
      );
  
      if (
        result.orderStatus === "LOADING"
      ) {
        setOrderStatus("LOADING");
        setOpenStage("LOADING");
      }
  
      if (nextStatus === "LOADED") {
        const vehicleIndex =
          vehicles.findIndex(
            (vehicle) =>
              vehicle.id ===
              statusEditor.vehicle.id
          ) + 1;
  
        log(
          `Vehicle ${vehicleIndex} loaded`
        );
      } else if (
        nextStatus === "LOADING"
      ) {
        log("Vehicle loading started");
      } else {
        log("Vehicle returned to pending");
      }
  
      setStatusEditor(null);
  
      notify(
        result.message ||
          "Vehicle status updated"
      );
    } catch (error) {
      console.error(
        "Unable to update vehicle status:",
        error
      );
  
      notify(
        error.message ||
          "Unable to update vehicle status."
      );
    }
  };

  const dispatch = async () => {
    if (!allLoaded) {
      notify(
        "All vehicles must be loaded before dispatch."
      );
      return;
    }
  
    try {
      const result =
        await dispatchAdminDeliveryOrder(
          ORDER.deliveryId,
          `${vehicles.length} vehicle${
            vehicles.length === 1
              ? ""
              : "s"
          } dispatched with ${
            totals.loadedQty
          } tons.`
        );
  
      const dispatchedVehicles =
        Array.isArray(result.vehicles)
          ? result.vehicles
          : [];
  
      setVehicles((currentVehicles) =>
        currentVehicles.map(
          (currentVehicle, index) => {
            const savedVehicle =
              dispatchedVehicles.find(
                (vehicle) =>
                  vehicle.id ===
                    currentVehicle.persistedId ||
                  vehicle.slotNumber ===
                    index + 1
              );
  
            if (!savedVehicle) {
              return {
                ...currentVehicle,
                status: "DISPATCHED",
                dispatchedAt:
                  result.dispatchedAt ||
                  new Date().toISOString(),
              };
            }
  
            return {
              ...currentVehicle,
  
              persistedId:
                savedVehicle.id ||
                currentVehicle.persistedId,
  
              status: String(
                savedVehicle.status ||
                  "DISPATCHED"
              ).toUpperCase(),
  
              loadedQty: Number(
                savedVehicle.loadedTons ||
                  currentVehicle.loadedQty ||
                  0
              ),
  
              loadedAt:
                savedVehicle.loadedAt ||
                currentVehicle.loadedAt,
  
              dispatchedAt:
                savedVehicle.dispatchedAt ||
                result.dispatchedAt ||
                new Date().toISOString(),
  
              deliveredAt:
                savedVehicle.deliveredAt ||
                null,
            };
          }
        )
      );
  
      setOrderStatus("IN_TRANSIT");
      setOpenStage("IN_TRANSIT");
      setDispatchConfirm(false);
  
      log("All vehicles dispatched");
  
      notify(
        result.message ||
          "Delivery order dispatched successfully."
      );
  
      onUpdated?.({
        ...selectedOrder,
        status: "IN_TRANSIT",
        dispatchedAt:
          result.dispatchedAt ||
          new Date().toISOString(),
        updatedAt:
          result.dispatchedAt ||
          new Date().toISOString(),
        vehicles: dispatchedVehicles,
      });
    } catch (error) {
      console.error(
        "Unable to dispatch delivery order:",
        error
      );
  
      setDispatchConfirm(false);
  
      notify(
        error.message ||
          "Unable to dispatch the delivery order."
      );
    }
  };
  const reopenLoading = async () => {
    const cleanedReason = String(
      reason || ""
    ).trim();
  
    if (!cleanedReason) {
      notify(
        "Correction reason is required"
      );
      return;
    }
  
    try {
      const result =
        await reopenAdminDeliveryLoading(
          ORDER.deliveryId,
          cleanedReason
        );
  
      const reopenedVehicles =
        Array.isArray(result.vehicles)
          ? result.vehicles
          : [];
  
      setVehicles(
        reopenedVehicles.map(
          (vehicle, index) => ({
            id:
              vehicle.id ||
              `VH-${String(
                vehicle.slotNumber ||
                  index + 1
              ).padStart(2, "0")}`,
  
            persistedId:
              vehicle.id || "",
  
            number:
              vehicle.vehicleNumber || "",
  
            driver:
              vehicle.driverName || "",
  
            phone:
              vehicle.driverPhone || "",
  
            materialId:
              vehicle.orderItemId || "",
  
            expectedQty: Number(
              vehicle.expectedTons || 0
            ),
  
            loadedQty: Number(
              vehicle.loadedTons || 0
            ),
  
            status: String(
              vehicle.status || "LOADED"
            ).toUpperCase(),
  
            loadedAt:
              vehicle.loadedAt || null,
  
            dispatchedAt:
              vehicle.dispatchedAt || null,
  
            deliveredAt:
              vehicle.deliveredAt || null,
          })
        )
      );
  
      setOrderStatus("LOADING");
      setOpenStage("LOADING");
      setReverseDispatch(false);
      setReason("");
  
      log(
        `Loading reopened: ${cleanedReason}`
      );
  
      onUpdated?.({
        ...selectedOrder,
  
        status: "LOADING",
  
        dispatchedAt: null,
  
        updatedAt:
          new Date().toISOString(),
  
        vehicles: reopenedVehicles,
      });
  
      notify(
        result.message ||
          "Loading stage reopened successfully."
      );
    } catch (error) {
      console.error(
        "Unable to reopen loading stage:",
        error
      );
  
      notify(
        error.message ||
          "Unable to reopen the loading stage."
      );
    }
  };
  const correctDelivery = () => { if (!reason.trim()) return notify("Correction reason is required"); setOrderStatus("IN_TRANSIT"); setOpenStage("IN_TRANSIT"); setDeliveryCorrection(false); log("Delivery status corrected"); setReason(""); notify("Order returned to In Transit"); };

  const stages = [
    { id: "CONFIRMED", label: "Order Confirmed", summary: `Loading scheduled for ${loadingDate}` },
    { id: "LOADING", label: "Loading", summary: `${totals.loadedVehicles} of ${vehicles.length} vehicles · ${totals.loadedQty} of ${totals.totalQty} t loaded` },
    { id: "IN_TRANSIT", label: "In Transit", summary: orderStatus === "IN_TRANSIT" || orderStatus === "DELIVERED" ? `${vehicles.length} vehicles dispatched` : "Waiting for all vehicles to load" },
    { id: "DELIVERED", label: "Delivered", summary: orderStatus === "DELIVERED" ? "Buyer confirmed delivery" : "Awaiting buyer confirmation" }
  ];

  return <div className="od-root">
    <style>{CSS}</style>
    <div className="od-bg"><i/><b/><span/><em/></div>

    <header className="od-header">
      <div className="od-width">
        <div className="od-top">
          <button className="od-icon" aria-label="Go back" onClick={() => onBack?.()}><Icon name="back"/></button>
          <div className="od-brand">
            <strong><Icon name="truck" size={17}/></strong>
            <span><b>StoneRate Admin</b><small>Delivery Operations</small></span>
          </div>
          <button className="od-icon od-icon-spin" aria-label="Refresh" onClick={() => { setNow(Date.now()); notify("Order refreshed"); }}><Icon name="refresh"/></button>
        </div>

        <h1>Active Order <span>Details</span></h1>

        <div className="od-id">
          <div>
            <b>{ORDER.deliveryId}<button type="button" aria-label="Copy delivery ID" onClick={() => copy(ORDER.deliveryId, "Delivery ID")}><Icon name="copy" size={11}/></button></b>
            <small>{ORDER.requestId}</small>
          </div>
          <em
  className={`status-${displayStatus.toLowerCase()}`}
>
  <i />

  {displayStatus.replace(
    /_/g,
    " "
  )}
</em>
        </div>

        <div className="od-time">
          <span><Icon name="clock" size={13}/>Updated {relative(activity[0]?.time, now)}</span>
          <b>{totals.loadedQty}/{totals.totalQty} t</b>
        </div>
        <div className="od-headbar"><i style={{ width: `${loadedPct}%` }}/></div>
      </div>
    </header>

    <main className="od-width od-main">
      <section className="od-progress">{stages.map((s, i) => <React.Fragment key={s.id}>
        <div className={`od-step ${i < currentRank ? "done" : i === currentRank ? "current" : "future"}`}>
          <span>{i < currentRank ? <Icon name="check" size={11}/> : i + 1}</span>
          <small>{s.label.replace("Order ", "")}</small>
        </div>
        {i < stages.length - 1 && <i className={i < currentRank ? "done" : ""}/>}
      </React.Fragment>)}</section>

      <section className="od-panel od-overview">
        <div className="od-head"><Icon name="cube" size={15}/><b>Order Overview</b><small>Read only accepted quotation</small></div>
        <div className="od-buyer">
          <div><strong>{ORDER.buyer.name}</strong><small>{ORDER.buyer.id}</small></div>
          <a href={`tel:${ORDER.buyer.phone.replace(/\s/g, "")}`}><Icon name="phone" size={14}/>Call</a>
        </div>
        <div className="od-address">
          <Icon name="pin" size={14}/><span>{ORDER.address}</span>
          <button aria-label="Copy address" onClick={() => copy(ORDER.address, "Address")}><Icon name="copy" size={13}/></button>
        </div>
        <div className="od-materials">
  {ORDER.materials.map((material) => (
    <article
      className="od-material-card"
      key={material.id}
    >
      <button
        type="button"
        className="od-material-main"
        onClick={() =>
          setMaterialDetail(material)
        }
        aria-label={`View reference for ${material.name}`}
      >
        {material.thumbnailUrl ||
        material.imageUrl
          ? React.createElement("img", {
              src:
                material.thumbnailUrl ||
                material.imageUrl,

              alt: `${material.name || "Material"} selected reference`,

              className:
                "od-material-thumbnail",
            })
          : (
              <MaterialArt
                material={material}
              />
            )}

        <span>
          <b>{material.name}</b>

          <small>
            {material.quantity} t
            {" · "}
            Source:{" "}
            {material.sourceArea ||
              "Not recorded"}
          </small>
        </span>
      </button>

      <button
  type="button"
  className="od-rate-button"
  onClick={() =>
    setMaterialRateDetail(material)
  }
  aria-label={`View rate details for ${material.name}`}
>
  {money(material.finalRate)}/t

  <Icon
    name="right"
    size={8}
  />
</button>
    </article>
  ))}
</div>
        <div className="od-overview-total">
          <span>Total quantity <b>{totals.totalQty} t</b></span>
          <span>Order value <b>{money(totals.orderValue)}</b></span>
        </div>
      </section>

      <section className="od-stages">{stages.map((stage, index) => {
        const locked = false;
        const completeStage = index < currentRank || (stage.id === "DELIVERED" && orderStatus === "DELIVERED");
        const open = openStage === stage.id;
        return <article className={`od-stage ${completeStage ? "complete" : ""} ${locked ? "locked" : ""} ${open ? "open" : ""}`} key={stage.id}>
          <button className="od-stage-toggle" disabled={locked} onClick={() => setOpenStage(open ? "" : stage.id)}>
            <span className="od-stage-icon">{locked ? <Icon name="lock" size={14}/> : completeStage ? <Icon name="check" size={14}/> : <Icon name={open ? "down" : "right"} size={14}/>}</span>
            <span><b>{stage.label}</b><small>{stage.summary}</small></span>
            <em>{locked ? "LOCKED" : completeStage ? "COMPLETE" : stage.id === orderStatus ? "CURRENT" : "PENDING"}</em>
          </button>

          {open && stage.id === "CONFIRMED" && <div className="od-stage-body">
            <div className="od-grid">
              <label>Confirmed at<input value={new Date(ORDER.confirmedAt).toLocaleString()} readOnly/></label>
              <label>Loading date<input type="date" value={loadingDate} min={new Date().toISOString().slice(0, 10)} max={tomorrow} onChange={e => setLoadingDate(e.target.value)}/></label>
              <label>Transporter<input value={ORDER.transporter} readOnly/></label>
              <label>Expected vehicles<input value={vehicles.length} readOnly/></label>
            </div>
            <button className="od-save" onClick={() => { log(`Loading rescheduled to ${loadingDate}`); notify("Loading schedule updated"); }}>Save Schedule</button>
          </div>}

          {open && stage.id === "LOADING" && <div className="od-stage-body">
          <div className="od-transporter-section">
  <div className="od-transporter-heading">
    <span>Transporter</span>
    <span>Vehicles</span>
    <span>Contact</span>
  </div>

  {transporterRows.length > 0 ? (
    transporterRows.map(
      (transporter, index) => (
        <div
          className="od-transporter-row"
          key={`${transporter.name}-${index}`}
        >
          <div className="od-transporter-info">
            <b>{transporter.name}</b>

            <small>
              {transporter.vehicleTypes.length > 0
                ? `${transporter.vehicleTypes.length} vehicle type${
                    transporter.vehicleTypes.length === 1
                      ? ""
                      : "s"
                  }`
                : "Breakdown unavailable"}
            </small>
          </div>

          <button
            type="button"
            className="od-vehicle-count-button"
            disabled={
              transporter.totalVehicles < 1
            }
            onClick={() =>
              setTransporterDetail(
                transporter
              )
            }
            aria-label={`View vehicle breakdown for ${transporter.name}`}
          >
            {transporter.totalVehicles}

            <Icon
              name="right"
              size={10}
            />
          </button>

          {transporter.phone ? (
            <button
              type="button"
              className="od-transporter-call"
              onClick={() => {
                const phoneNumber =
                  String(
                    transporter.phone
                  ).replace(/\D/g, "");

                window.location.href =
                  `tel:${phoneNumber}`;
              }}
            >
              <Icon
                name="phone"
                size={12}
              />

              Call
            </button>
          ) : (
            <span className="od-phone-unavailable">
              Not recorded
            </span>
          )}
        </div>
      )
    )
  ) : (
    <div className="od-transporter-empty">
      Transporter information is not
      available.
    </div>
  )}
</div>
            <div className="od-loading-summary">
              <div><span>Vehicles loaded</span><b>{totals.loadedVehicles}/{vehicles.length}</b></div>
              <div><span>Quantity loaded</span><b>{totals.loadedQty}/{totals.totalQty} t</b></div>
              <div className="od-bar"><i style={{ width: `${loadedPct}%` }}/></div>
            </div>
            <div className="od-material-progress">{totals.byMaterial.map(m => <div key={m.id}>
              <span><b>{m.name}</b><small>{m.loaded}/{m.quantity} t loaded</small></span>
              <strong className={m.loaded >= m.quantity ? "done" : ""}>{m.loaded >= m.quantity ? "Complete" : `${m.quantity - m.loaded} t left`}</strong>
            </div>)}</div>
            <div className="od-vehicle-list">{vehicles.map((v, i) => {
              const material = ORDER.materials.find(m => m.id === v.materialId);
              return <article className={`od-vehicle v-${v.status.toLowerCase()}`} key={v.id}>
                <div className="od-vehicle-head">
                  <span><b>Vehicle {i + 1}</b><small>{v.number || "Details not added"}</small></span>
                  <em>{v.status}</em>
                </div>
                {v.number ? <>
                  <div className="od-vehicle-info">
                    <span><b>{v.driver}</b><small>{v.phone}</small></span>
                    <a href={`tel:${v.phone.replace(/\s/g, "")}`}><Icon name="phone" size={13}/></a>
                  </div>
                  <div className="od-vehicle-meta">
                    <span>{material?.name}</span>
                    <b>{v.status === "LOADED" ? v.loadedQty : v.expectedQty} t</b>
                    <small>{v.loadedAt ? relative(v.loadedAt, now) : "Not loaded"}</small>
                  </div>
                  <div className="od-vehicle-actions">
                    <button onClick={() => { setFormErrors({}); setVehicleForm({ ...v }); }}><Icon name="edit" size={13}/>Edit details</button>
                    <button onClick={() => setStatusEditor({ vehicle: v, status: v.status === "LOADED" ? "LOADING" : "LOADED", loadedQty: v.loadedQty || v.expectedQty, reason: "" })}>Change status</button>
                  </div>
                </> : <button className="od-add-vehicle" onClick={() => { setFormErrors({}); setVehicleForm({ ...v }); }}><Icon name="plus" size={14}/>Add vehicle and driver details</button>}
              </article>;
            })}</div>
            {totals.remainingToAllocate > 0 &&
  orderStatus === "LOADING" && (
    <button
      type="button"
      className="od-add-another-vehicle"
      onClick={
        addAnotherVehicleSlot
      }
    >
      <span className="od-add-another-title">
        <Icon
          name="plus"
          size={15}
        />

        Add Another Vehicle
      </span>

      <small>
        {totals.remainingToAllocate.toLocaleString(
          "en-IN"
        )}{" "}
        t still needs vehicle allocation
      </small>
    </button>
  )}

{allLoaded && (
  <button
    type="button"
    className="od-dispatch"
    onClick={() =>
      setDispatchConfirm(true)
    }
  >
    All Loaded · Dispatch Order
  </button>
)}
          </div>}

          {open && stage.id === "IN_TRANSIT" && <div className="od-stage-body">
            <div className="od-transit-card">
              <Icon name="route" size={22}/>
              <div>
                <b>{orderStatus === "IN_TRANSIT" || orderStatus === "DELIVERED" ? "All vehicles are in route" : "Waiting for all vehicles to load"}</b>
                <small>{orderStatus === "IN_TRANSIT" || orderStatus === "DELIVERED"
                  ? `${vehicles.length} vehicles · ${totals.loadedQty} t · Destination Hoskote`
                  : `${totals.loadedVehicles} of ${vehicles.length} vehicles · ${totals.loadedQty} of ${totals.totalQty} t loaded · ${totals.totalQty - totals.loadedQty} t remaining`}</small>
              </div>
            </div>
            {vehicles.filter(v => v.number).map(v => <div className="od-route-row" key={v.id}>
              <span><b>{v.number}</b><small>{v.driver} · {ORDER.materials.find(m => m.id === v.materialId)?.name}</small></span>
              <a href={`tel:${v.phone.replace(/\s/g, "")}`}><Icon name="phone" size={13}/>Call</a>
            </div>)}
            {orderStatus === "IN_TRANSIT" && <>
              <div className="od-awaiting">
                <Icon name="clock" size={15}/>
                <span><b>Awaiting buyer delivery confirmation</b><small>Admin cannot normally complete delivery.</small></span>
              </div>
              <button className="od-correction" onClick={() => { setReason(""); setReverseDispatch(true); }}>Reopen Loading Stage</button>
            </>}
          </div>}

          {open && stage.id === "DELIVERED" && <div className="od-stage-body">
            <div className="od-delivered">
              <Icon name="check" size={24}/>
              <div>
                <b>{orderStatus === "DELIVERED" ? "Delivery confirmed by buyer" : "Awaiting buyer confirmation"}</b>
                <small>{orderStatus === "DELIVERED" ? `${totals.totalQty} t received · ${vehicles.length} vehicles` : "This stage updates automatically when the buyer confirms delivery."}</small>
              </div>
            </div>
            {orderStatus === "DELIVERED" && <button className="od-correction" onClick={() => { setReason(""); setDeliveryCorrection(true); }}>Correct Delivery Status</button>}
          </div>}
        </article>;
      })}</section>

      <section className="od-panel od-activity">
      <div className="od-head">
  <Icon name="history" size={15} />
  <b>Activity Log</b>
</div>
        {issue && <div className="od-issue"><Icon name="alert" size={14}/><span>{issue}</span></div>}
        {activity.slice(0, 6).map((a, i) => <div className="od-log" key={`${a.time}-${i}`}>
          <i/><span><b>{a.text}</b><small>{relative(a.time, now)}</small></span>
        </div>)}
      </section>
    </main>]
    {transporterDetail && (
  <div
    className="od-overlay"
    onMouseDown={() =>
      setTransporterDetail(null)
    }
  >
    <section
      className="od-modal od-transporter-modal"
      onMouseDown={(event) =>
        event.stopPropagation()
      }
    >
      <div className="od-sheet-head">
        <div>
          <b>Vehicle Breakdown</b>

          <small>
            {transporterDetail.name}
          </small>
        </div>

        <button
          type="button"
          aria-label="Close vehicle breakdown"
          onClick={() =>
            setTransporterDetail(null)
          }
        >
          <Icon name="close" />
        </button>
      </div>

      <div className="od-breakdown-list">
        {transporterDetail.vehicleTypes.map(
          (vehicleType, index) => (
            <div
              className="od-breakdown-row"
              key={
                vehicleType.vehicleName ||
                index
              }
            >
              <div>
                <b>
                  {vehicleType.vehicleName}
                </b>

                {vehicleType.capacityTons >
                  0 && (
                  <small>
                    {vehicleType.capacityTons}
                    {" "}t capacity
                  </small>
                )}
              </div>

              <strong>
                {vehicleType.quantity}
                {" "}
                {vehicleType.quantity === 1
                  ? "vehicle"
                  : "vehicles"}
              </strong>
            </div>
          )
        )}
      </div>

      <div className="od-breakdown-total">
        <span>Total vehicles</span>

        <strong>
          {transporterDetail.totalVehicles}
        </strong>
      </div>

      <button
        type="button"
        className="od-breakdown-close"
        onClick={() =>
          setTransporterDetail(null)
        }
      >
        Close
      </button>
    </section>
  </div>
)}


    {materialRateDetail && (
  <div
    className="od-overlay"
    onMouseDown={() =>
      setMaterialRateDetail(null)
    }
  >
    <section
      className="od-sheet od-rate-sheet"
      onMouseDown={(event) =>
        event.stopPropagation()
      }
    >
      <div className="od-sheet-head">
        <div>
          <b>Rate Details</b>

          <small>
            {materialRateDetail.name}
          </small>
        </div>

        <button
          type="button"
          aria-label="Close rate details"
          onClick={() =>
            setMaterialRateDetail(null)
          }
        >
          <Icon name="close" />
        </button>
      </div>

      <section className="od-cost-section">
        <h3>Material Cost</h3>

        <div className="od-cost-row">
          <span>Material rate per ton</span>

          <b>
            {money(
              materialRateDetail
                .materialRatePerTon
            )}
            /t
          </b>
        </div>

        <div className="od-cost-row">
          <span>Material quantity</span>

          <b>
            {materialRateDetail.quantity}
            {" "}t
          </b>
        </div>

        <div className="od-cost-row">
          <span>Material subtotal</span>

          <b>
            {money(
              Number(
                materialRateDetail
                  .materialRatePerTon || 0
              ) *
                Number(
                  materialRateDetail
                    .quantity || 0
                )
            )}
          </b>
        </div>
      </section>

      <section className="od-cost-section">
        <h3>Permit Cost</h3>

        <div className="od-cost-row">
          <span>Permit rate per ton</span>

          <b
            className={
              materialRateDetail
                .permitRatePerTon === null
                ? "od-cost-empty"
                : ""
            }
          >
            {materialRateDetail
              .permitRatePerTon === null
              ? "Not entered"
              : `${money(
                  materialRateDetail
                    .permitRatePerTon
                )}/t`}
          </b>
        </div>

        <div className="od-cost-row">
          <span>Permit subtotal</span>

          <b
            className={
              materialRateDetail
                .permitRatePerTon === null
                ? "od-cost-empty"
                : ""
            }
          >
            {materialRateDetail
              .permitRatePerTon === null
              ? "Not entered"
              : money(
                  Number(
                    materialRateDetail
                      .permitRatePerTon || 0
                  ) *
                    Number(
                      materialRateDetail
                        .quantity || 0
                    )
                )}
          </b>
        </div>
      </section>

      <section className="od-cost-section">
        <h3>Transportation</h3>

        <div className="od-cost-row">
          <span>Transporter</span>

          <b>
            {materialRateDetail
              .transporter ||
              "Not assigned"}
          </b>
        </div>

        <div className="od-cost-row">
          <span>Calculation method</span>

          <b>
            {materialRateDetail
              .transportMethod ||
              "Not recorded"}
          </b>
        </div>

        <div className="od-cost-row">
          <span>Entered transport rate</span>

          <b>
            {money(
              materialRateDetail
                .transportRate
            )}
          </b>
        </div>

        <div className="od-cost-row">
          <span>Transportation total</span>

          <b>
            {money(
              materialRateDetail
                .transportTotal
            )}
          </b>
        </div>

        <div className="od-cost-row">
          <span>Transportation per ton</span>

          <b>
            {money(
              materialRateDetail
                .transportPerTon
            )}
            /t
          </b>
        </div>
      </section>

      <section className="od-final-rate-card">
        <div>
          <span>Final rate per ton</span>

          <small>
            Material, permit, and
            transportation included
          </small>
        </div>

        <strong>
          {money(
            materialRateDetail.finalRate
          )}
          /t
        </strong>
      </section>

      <section className="od-material-total-card">
        <span>Material total</span>

        <strong>
          {money(
            Number(
              materialRateDetail
                .finalRate || 0
            ) *
              Number(
                materialRateDetail
                  .quantity || 0
              )
          )}
        </strong>
      </section>
    </section>
  </div>
)}

    {materialDetail && <div className="od-overlay" onMouseDown={() => setMaterialDetail(null)}>
      <section className="od-sheet od-material-sheet" onMouseDown={e => e.stopPropagation()}>
        <div className="od-sheet-head">
          <div><b>Material Details</b><small>{materialDetail.referenceId}</small></div>
          <button onClick={() => setMaterialDetail(null)}><Icon name="close"/></button>
        </div>
        <div className="od-material-large">
  {materialDetail.imageUrl
    ? React.createElement("img", {
        src: materialDetail.imageUrl,
        alt: `${
          materialDetail.name || "Material"
        } selected reference`,
        className:
          "od-material-real-image",
      })
    : (
        <MaterialArt
          material={materialDetail}
        />
      )}
</div>
        <dl>
          <div><dt>Material</dt><dd>{materialDetail.name}</dd></div>
          <div><dt>Quantity</dt><dd>{materialDetail.quantity} t</dd></div>
          <div><dt>Supplier</dt><dd>{materialDetail.seller}</dd></div>
          <div><dt>Supplier mobile</dt><dd>{materialDetail.sellerPhone}</dd></div>
          <div><dt>Image uploaded</dt><dd>{new Date(materialDetail.imageUploadedAt).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}</dd></div>
          <div><dt>Final rate</dt><dd>{money(materialDetail.finalRate)}/t</dd></div>
          <div><dt>Material total</dt><dd>{money(materialDetail.quantity * materialDetail.finalRate)}</dd></div>
          <div><dt>Reference ID</dt><dd>{materialDetail.referenceId}</dd></div>
        </dl>
        <div className="od-material-actions">
  {materialDetail.sellerPhone ? (
    <>
      <button
        type="button"
        onClick={() =>
          copy(
            materialDetail.sellerPhone,
            "Supplier number"
          )
        }
      >
        <Icon name="copy" size={14} />
        Copy Number
      </button>

      <button
        type="button"
        onClick={() => {
          const phoneNumber = String(
            materialDetail.sellerPhone
          ).replace(/\s/g, "");

          window.location.href =
            `tel:${phoneNumber}`;
        }}
      >
        <Icon name="phone" size={14} />
        Call Supplier
      </button>
    </>
  ) : (
    <div className="od-source-only">
      No supplier contact was recorded for
      this material.
    </div>
  )}
</div>

      </section>
    </div>}

    {vehicleForm && <div className="od-overlay">
      <section className="od-sheet">
        <div className="od-sheet-head">
          <div><b>{vehicleForm.number ? "Edit Vehicle Details" : "Add Vehicle Details"}</b><small>{vehicleForm.id}</small></div>
          <button onClick={() => setVehicleForm(null)}><Icon name="close"/></button>
        </div>
        <div className="od-form">
          <label>Vehicle number
            <input maxLength="13" value={vehicleForm.number} placeholder="KA 01 AB 4582" onChange={e => setVehicleForm({ ...vehicleForm, number: e.target.value.toUpperCase().replace(/[^A-Z0-9 ]/g, "") })}/>
            {formErrors.number && <em>{formErrors.number}</em>}
          </label>
          <label>Driver name
            <input value={vehicleForm.driver} placeholder="Ramesh Kumar" onChange={e => setVehicleForm({ ...vehicleForm, driver: e.target.value.replace(/[^A-Za-z .'-]/g, "") })}/>
            {formErrors.driver && <em>{formErrors.driver}</em>}
          </label>
          <label>Driver mobile
            <div className="od-phone-input">
              <b>+91</b>
              <input inputMode="numeric" maxLength="10" value={String(vehicleForm.phone || "").replace(/\D/g, "").slice(-10)} placeholder="9876543210" onChange={e => setVehicleForm({ ...vehicleForm, phone: e.target.value.replace(/\D/g, "").slice(0, 10) })}/>
            </div>
            {formErrors.phone && <em>{formErrors.phone}</em>}
          </label>
          <label>Material
            <select value={vehicleForm.materialId} onChange={e => setVehicleForm({ ...vehicleForm, materialId: e.target.value, expectedQty: "" })}>
              {ORDER.materials.map(m => <option value={m.id} key={m.id}>{m.name}</option>)}
            </select>
            {formErrors.materialId && <em>{formErrors.materialId}</em>}
          </label>
          <label>Expected load (t)
            <input type="number" min="0.1" step="0.1" value={vehicleForm.expectedQty} onChange={e => setVehicleForm({ ...vehicleForm, expectedQty: e.target.value })}/>
            <small>Remaining: {Math.max(0, (ORDER.materials.find(m => m.id === vehicleForm.materialId)?.quantity || 0) - vehicles.filter(v => v.id !== vehicleForm.id && v.materialId === vehicleForm.materialId).reduce((sum, v) => sum + Number(v.expectedQty || 0), 0))} t</small>
            {formErrors.expectedQty && <em>{formErrors.expectedQty}</em>}
          </label>
        </div>
        <div className="od-dual">
          <button onClick={() => setVehicleForm(null)}>Cancel</button>
          <button className="od-primary" onClick={() => saveVehicle(vehicleForm)}>Save Vehicle</button>
        </div>
      </section>
    </div>}

    {statusEditor && <div className="od-overlay">
      <section className="od-modal">
        <h3>Update Vehicle Status</h3>
        <p>{statusEditor.vehicle.number || statusEditor.vehicle.id}</p>
        <div className="od-status-options">{["PENDING", "LOADING", "LOADED"].map(s => <label key={s}>
          <input type="radio" checked={statusEditor.status === s} onChange={() => setStatusEditor({ ...statusEditor, status: s })}/>{s}
        </label>)}</div>
        {statusEditor.status === "LOADED" && <label className="od-field">Loaded quantity (t)
          <input type="number" value={statusEditor.loadedQty} onChange={e => setStatusEditor({ ...statusEditor, loadedQty: e.target.value })}/>
        </label>}
        <label className="od-field">Reason for change (optional)
          <textarea value={statusEditor.reason} onChange={e => setStatusEditor({ ...statusEditor, reason: e.target.value })} placeholder="Optional note"/>
        </label>
        <div className="od-dual">
          <button onClick={() => setStatusEditor(null)}>Cancel</button>
          <button className="od-primary" onClick={updateVehicleStatus}>Confirm Update</button>
        </div>
      </section>
    </div>}

    {dispatchConfirm && <div className="od-overlay">
      <section className="od-modal od-confirm">
        <span><Icon name="route"/></span>
        <h3>Dispatch all vehicles?</h3>
        <p>{vehicles.length} vehicles carrying {totals.loadedQty} t will move to In Transit.</p>
        <div className="od-dual">
          <button onClick={() => setDispatchConfirm(false)}>Cancel</button>
          <button className="od-primary" onClick={dispatch}>Confirm Dispatch</button>
        </div>
      </section>
    </div>}

    {reverseDispatch && <div className="od-overlay">
      <section className="od-modal">
        <h3>Reopen Loading Stage?</h3>
        <p>This will move the order from In Transit back to Loading.</p>
        <label className="od-field">Correction reason
          <textarea value={reason} onChange={e => setReason(e.target.value)} placeholder="Required"/>
        </label>
        <div className="od-dual">
          <button onClick={() => setReverseDispatch(false)}>Cancel</button>
          <button className="od-danger" onClick={reopenLoading}>Reopen Loading</button>
        </div>
      </section>
    </div>}

    {deliveryCorrection && <div className="od-overlay">
      <section className="od-modal">
        <h3>Correct Delivery Status?</h3>
        <p>This authorized correction returns the order to In Transit.</p>
        <label className="od-field">Correction reason
          <textarea value={reason} onChange={e => setReason(e.target.value)} placeholder="Required"/>
        </label>
        <div className="od-dual">
          <button onClick={() => setDeliveryCorrection(false)}>Cancel</button>
          <button className="od-danger" onClick={correctDelivery}>Confirm Correction</button>
        </div>
      </section>
    </div>}

    {issueModal && <div className="od-overlay">
      <section className="od-modal">
        <h3>Report Operational Issue</h3>
        <div className="od-status-options">{["Vehicle unavailable", "Driver unavailable", "Material quantity unavailable", "Loading delayed", "Vehicle breakdown", "Delivery delayed", "Quantity mismatch", "Other"].map(x => <label key={x}>
          <input type="radio" checked={issue === x} onChange={() => setIssue(x)}/>{x}
        </label>)}</div>
        <div className="od-dual">
          <button onClick={() => setIssueModal(false)}>Cancel</button>
          <button className="od-primary" disabled={!issue} onClick={() => { log(`Issue reported: ${issue}`); setIssueModal(false); notify("Issue reported"); }}>Report Issue</button>
        </div>
      </section>
    </div>}

    <div className={`od-toast${toast ? " show" : ""}`}>{toast}</div>
  </div>;
}

const CSS = `
.od-root{
  --o:#f97316;--o2:#c2560b;--o3:#fbbf24;--soft:rgba(249,115,22,.11);
  --green:#1f9463;--green2:#0f7a4c;--red:#d64545;--blue:#2563eb;--teal:#0d9488;--amber:#e08b1e;
  --ink:#141a24;--muted:#6b7687;--faint:#96a0af;--line:#e9edf3;--line2:#dbe2ec;
  --card:rgba(255,255,255,.86);
  --glass:saturate(180%) blur(18px);
  --sh-s:0 1px 2px rgba(18,28,45,.05),0 2px 8px rgba(18,28,45,.05);
  --sh-m:0 2px 6px rgba(18,28,45,.05),0 12px 28px -10px rgba(18,28,45,.16);
  --sh-l:0 24px 56px -18px rgba(16,26,44,.35);
  --ring:0 0 0 3px rgba(249,115,22,.18);
  min-height:100dvh;color:var(--ink);background:#eff3f9;
  font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
}
.od-root *{box-sizing:border-box}
.od-root button,.od-root input,.od-root select,.od-root textarea{font:inherit}
.od-root button{cursor:pointer;transition:transform .18s cubic-bezier(.2,.8,.3,1),box-shadow .18s ease,background .18s ease,border-color .18s ease,color .18s ease,opacity .18s ease}
.od-root button:active:not(:disabled){transform:translateY(1px) scale(.99)}
.od-root button:disabled{cursor:not-allowed}
.od-root :focus-visible{outline:0;box-shadow:var(--ring);border-radius:10px}
.od-root ::selection{background:rgba(249,115,22,.22)}
.od-root ::-webkit-scrollbar{width:9px;height:9px}
.od-root ::-webkit-scrollbar-thumb{border:3px solid transparent;border-radius:9px;background:rgba(24,42,72,.22);background-clip:content-box}

/* ---------- ambient background ---------- */
.od-bg{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}
.od-bg>i{position:absolute;inset:0;
  background:linear-gradient(transparent 0 31px,rgba(24,42,72,.045) 31px 32px),linear-gradient(90deg,transparent 0 31px,rgba(24,42,72,.045) 31px 32px);
  background-size:32px 32px;
  mask-image:radial-gradient(120% 85% at 50% 0%,#000 18%,transparent 76%);
  -webkit-mask-image:radial-gradient(120% 85% at 50% 0%,#000 18%,transparent 76%)}
.od-bg>b,.od-bg>span,.od-bg>em{position:absolute;border-radius:50%;filter:blur(62px);opacity:.55;will-change:transform}
.od-bg>b{width:46vw;height:46vw;left:-10vw;top:-17vw;background:radial-gradient(circle,rgba(255,168,74,.6),transparent 66%);animation:odFloatA 22s ease-in-out infinite}
.od-bg>span{width:42vw;height:42vw;right:-11vw;top:-7vw;background:radial-gradient(circle,rgba(80,140,255,.46),transparent 66%);animation:odFloatB 26s ease-in-out infinite}
.od-bg>em{width:38vw;height:38vw;left:32vw;top:26vw;background:radial-gradient(circle,rgba(13,148,136,.3),transparent 68%);animation:odFloatA 30s ease-in-out infinite reverse}
@keyframes odFloatA{0%,100%{transform:translate3d(0,0,0) scale(1)}50%{transform:translate3d(3vw,2vw,0) scale(1.08)}}
@keyframes odFloatB{0%,100%{transform:translate3d(0,0,0) scale(1)}50%{transform:translate3d(-3vw,3vw,0) scale(1.06)}}
.od-transporter-modal {
  padding: 17px;
}

.od-breakdown-list {
  margin-top: 14px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: #fff;
}

.od-breakdown-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 11px 12px;
  border-bottom: 1px solid var(--line);
}

.od-breakdown-row:last-child {
  border-bottom: 0;
}

.od-breakdown-row > div {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.od-breakdown-row b {
  color: var(--ink);
  font-size: 11px;
  font-weight: 850;
}

.od-breakdown-row small {
  margin-top: 2px;
  color: var(--faint);
  font-size: 8.5px;
}

.od-breakdown-row strong {
  color: var(--o2);
  font-size: 10px;
  font-weight: 900;
  white-space: nowrap;
}

.od-breakdown-total {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  padding: 11px 12px;
  border: 1px solid
    rgba(31, 148, 99, 0.22);
  border-radius: 12px;
  background:
    rgba(31, 148, 99, 0.09);
}

.od-breakdown-total span {
  color: var(--green2);
  font-size: 10px;
  font-weight: 800;
}

.od-breakdown-total strong {
  color: var(--green2);
  font-size: 15px;
  font-weight: 900;
}

.od-breakdown-close {
  width: 100%;
  min-height: 40px;
  margin-top: 12px;
  border: 0;
  border-radius: 11px;
  background:
    linear-gradient(
      135deg,
      var(--o3),
      var(--o),
      var(--o2)
    );
  color: #fff;
  font-size: 10px;
  font-weight: 850;
}

.od-width{width:min(100%,980px);margin:auto;position:relative;z-index:1}

/* ---------- header ---------- */
.od-header{position:sticky;top:0;z-index:20;border-bottom:1px solid rgba(16,28,50,.07);
  background:linear-gradient(180deg,rgba(252,253,255,.9),rgba(239,243,249,.72));
  backdrop-filter:var(--glass);-webkit-backdrop-filter:var(--glass);
  box-shadow:0 1px 0 rgba(255,255,255,.7) inset,0 10px 26px -22px rgba(16,26,44,.6)}
.od-header .od-width{padding:12px 14px 14px}
.od-top{display:flex;align-items:center;gap:10px}
.od-icon{width:38px;height:38px;display:grid;place-items:center;border:1px solid var(--line2);border-radius:12px;
  background:linear-gradient(180deg,#fff,#f6f8fc);color:var(--ink);box-shadow:var(--sh-s)}
.od-icon:hover{border-color:rgba(249,115,22,.45);color:var(--o2);box-shadow:0 6px 16px -8px rgba(194,86,11,.6);transform:translateY(-1px)}
.od-icon-spin:hover svg{animation:odSpin .7s cubic-bezier(.4,0,.2,1)}
@keyframes odSpin{to{transform:rotate(360deg)}}
.od-brand{display:flex;align-items:center;gap:10px;flex:1;min-width:0}
.od-brand>strong{position:relative;width:38px;height:38px;display:grid;place-items:center;border-radius:12px;color:#fff;
  background:linear-gradient(135deg,var(--o3),var(--o) 45%,var(--o2));
  box-shadow:0 8px 18px -8px rgba(194,86,11,.85),0 0 0 1px rgba(255,255,255,.35) inset}
.od-brand>strong::after{content:"";position:absolute;inset:0;border-radius:12px;background:linear-gradient(180deg,rgba(255,255,255,.4),transparent 55%)}
.od-brand span{display:flex;flex-direction:column;min-width:0}
.od-brand b{font-size:14.5px;font-weight:800;letter-spacing:-.01em}
.od-brand small{font-size:9.5px;color:var(--o2);font-weight:800;letter-spacing:.11em;text-transform:uppercase}
.od-header h1{margin:14px 0 0;font-size:29px;font-weight:850;letter-spacing:-.038em;line-height:1.1}
.od-header h1 span{background:linear-gradient(100deg,var(--o),var(--o3) 45%,var(--o2));background-size:200% auto;
  background-clip:text;-webkit-background-clip:text;color:transparent;animation:odShine 6s linear infinite}
@keyframes odShine{to{background-position:200% center}}
.od-material-real-image {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
  border-radius: 16px;
  background: #f4f7fb;
}

.od-id,.od-time{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:10px}
.od-id>div{display:flex;flex-direction:column;min-width:0}
.od-id b{display:flex;align-items:center;gap:6px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;letter-spacing:.02em}
.od-id b button{width:22px;height:22px;display:grid;place-items:center;border:1px solid var(--line2);border-radius:7px;color:var(--faint);background:rgba(255,255,255,.8)}
.od-id b button:hover{color:var(--o2);border-color:rgba(249,115,22,.4);background:#fff}
.od-id small{margin-top:1px;font-size:9px;color:var(--faint);letter-spacing:.04em}
.od-id em{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;font-size:9px;font-weight:850;font-style:normal;
  letter-spacing:.09em;text-transform:uppercase;white-space:nowrap;border:1px solid transparent;box-shadow:var(--sh-s)}
.od-id em>i{width:6px;height:6px;border-radius:50%;background:currentColor;box-shadow:0 0 0 0 currentColor;animation:odPulse 2.2s ease-out infinite}
@keyframes odPulse{0%{box-shadow:0 0 0 0 rgba(0,0,0,.28)}70%{box-shadow:0 0 0 6px rgba(0,0,0,0)}100%{box-shadow:0 0 0 0 rgba(0,0,0,0)}}
.status-loaded {
  color: var(--green2);
  background: linear-gradient(
    180deg,
    #eafaf2,
    #d9f3e6
  );
  border-color: rgba(
    31,
    148,
    99,
    0.26
  ) !important;
}
.status-loading{color:#a15c07;background:linear-gradient(180deg,#fff6e6,#fdecd0);border-color:rgba(224,139,30,.28)!important}
.status-in_transit{color:#08776d;background:linear-gradient(180deg,#eefcfa,#dbf6f2);border-color:rgba(13,148,136,.26)!important}
.status-delivered{color:var(--green2);background:linear-gradient(180deg,#eafaf2,#d9f3e6);border-color:rgba(31,148,99,.26)!important}

.od-time{margin-top:8px;font-size:10.5px;color:var(--muted);font-weight:600}
.od-time span{display:flex;align-items:center;gap:5px}
.od-time>b{padding:3px 9px;border-radius:999px;color:var(--o2);background:var(--soft);font-size:10.5px;font-weight:850;font-variant-numeric:tabular-nums}
.od-headbar{height:4px;margin-top:9px;border-radius:9px;background:rgba(24,42,72,.09);overflow:hidden}
.od-headbar i{display:block;height:100%;border-radius:9px;
  background:linear-gradient(90deg,var(--o),var(--o3),var(--o));background-size:200% 100%;
  transition:width .7s cubic-bezier(.2,.8,.3,1);animation:odShine 3s linear infinite}

.od-main{padding:16px 14px 34px}

/* ---------- stepper ---------- */
.od-progress{display:flex;align-items:center;margin-bottom:12px;padding:13px 14px;border:1px solid rgba(255,255,255,.75);border-radius:18px;
  background:var(--card);backdrop-filter:var(--glass);-webkit-backdrop-filter:var(--glass);box-shadow:var(--sh-m)}
.od-progress>i{position:relative;height:3px;flex:1;margin:0 2px;border-radius:9px;background:var(--line2);overflow:hidden}
.od-progress>i.done{background:linear-gradient(90deg,var(--green),#34c184)}
.od-step{display:flex;flex-direction:column;align-items:center;gap:5px}
.od-step>span{position:relative;width:28px;height:28px;display:grid;place-items:center;border-radius:50%;color:var(--faint);
  background:#eef2f6;font-size:10px;font-weight:850;box-shadow:0 0 0 1px rgba(24,42,72,.05) inset;
  transition:transform .25s cubic-bezier(.2,.8,.3,1),box-shadow .25s ease,background .25s ease,color .25s ease}
.od-step small{font-size:8.5px;font-weight:700;color:var(--faint);letter-spacing:.02em;white-space:nowrap}
.od-step.done>span{color:#fff;background:linear-gradient(135deg,#34c184,var(--green));box-shadow:0 6px 14px -6px rgba(31,148,99,.8)}
.od-step.done small{color:var(--green2)}
.od-step.current>span{color:#fff;background:linear-gradient(135deg,var(--o3),var(--o) 55%,var(--o2));
  box-shadow:0 0 0 5px var(--soft),0 8px 18px -8px rgba(194,86,11,.9);transform:scale(1.08)}
.od-step.current small{color:var(--o2);font-weight:850}




.od-transporter-info span {
  color: var(--faint);
  font-size: 8px;
  font-weight: 850;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.od-transporter-info b {
  margin-top: 3px;
  overflow: hidden;
  color: var(--ink);
  font-size: 12px;
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.od-transporter-call:hover {
  background:
    rgba(31, 148, 99, 0.17);
  transform: translateY(-1px);
}

.od-transporter-section {
  margin-bottom: 12px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 14px;
  background:
    linear-gradient(
      180deg,
      #ffffff,
      #f7f9fc
    );
}



.od-transporter-heading span {
  color: var(--faint);
  font-size: 7.5px;
  font-weight: 900;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.od-transporter-heading span:nth-child(2),
.od-transporter-heading span:nth-child(3) {
  text-align: center;
}



.od-transporter-row:last-child {
  border-bottom: 0;
}

.od-transporter-info {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.od-transporter-info b {
  overflow: hidden;
  color: var(--ink);
  font-size: 11.5px;
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.od-transporter-info small {
  margin-top: 2px;
  color: var(--faint);
  font-size: 8.5px;
}



.od-vehicle-count-button:hover:not(
  :disabled
) {
  border-color: var(--o);
  background:
    rgba(249, 115, 22, 0.16);
  transform: translateY(-1px);
}

.od-vehicle-count-button:disabled {
  opacity: 0.45;
  cursor: default;
}

.od-transporter-call:hover {
  background:
    rgba(31, 148, 99, 0.17);
  transform: translateY(-1px);
}

.od-transporter-heading {
  display: grid;
  grid-template-columns:
    minmax(0, 3fr) 1fr 1fr;
  align-items: center;
  gap: 4px;
  padding: 8px 11px;
  border-bottom: 1px solid var(--line);
  background: #f4f7fb;
}

.od-transporter-heading span {
  color: var(--faint);
  font-size: 7.5px;
  font-weight: 900;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.od-transporter-heading span:nth-child(2),
.od-transporter-heading span:nth-child(3) {
  text-align: center;
}

.od-transporter-row {
  display: grid;
  grid-template-columns:
    minmax(0, 3fr) 1fr 1fr;
  align-items: center;
  gap: 4px;
  min-height: 55px;
  padding: 9px 11px;
  border-bottom: 1px solid var(--line);
}

.od-transporter-row:last-child {
  border-bottom: 0;
}

.od-transporter-info {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.od-transporter-info b {
  overflow: hidden;
  color: var(--ink);
  font-size: 11.5px;
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.od-transporter-info small {
  margin-top: 2px;
  color: var(--faint);
  font-size: 8px;
}

.od-vehicle-count-button {
  min-width: 0;
  min-height: 26px;
  justify-self: center;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--o2);
  font-size: 12px;
  font-weight: 900;
  box-shadow: none;
}

.od-vehicle-count-button:hover:not(:disabled) {
  background: transparent;
  color: var(--o);
  transform: translateX(1px);
  box-shadow: none;
}

.od-vehicle-count-button:disabled {
  opacity: 0.45;
  cursor: default;
}

.od-transporter-call {
  min-width: 0;
  min-height: 26px;
  justify-self: center;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--green2);
  font-size: 8.5px;
  font-weight: 850;
  box-shadow: none;
}

.od-transporter-call:hover {
  background: transparent;
  color: var(--green);
  transform: translateY(-1px);
  box-shadow: none;
}

.od-phone-unavailable {
  justify-self: center;
  overflow: hidden;
  max-width: 100%;
  color: var(--faint);
  font-size: 7.5px;
  font-weight: 700;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.od-transporter-empty {
  padding: 12px;
  color: var(--faint);
  font-size: 9.5px;
  text-align: center;
}

/* ---------- panels & cards ---------- */
.od-panel,.od-stage{position:relative;margin-bottom:12px;border:1px solid rgba(255,255,255,.8);border-radius:18px;
  background:var(--card);backdrop-filter:var(--glass);-webkit-backdrop-filter:var(--glass);
  box-shadow:var(--sh-m);transition:box-shadow .25s ease,transform .25s cubic-bezier(.2,.8,.3,1),border-color .25s ease}
.od-panel:hover,.od-stage:hover{box-shadow:0 3px 8px rgba(18,28,45,.06),0 20px 40px -18px rgba(18,28,45,.28)}
.od-panel{padding:14px}
.od-overview::before{content:"";position:absolute;left:0;right:0;top:0;height:3px;border-radius:18px 18px 0 0;
  background:linear-gradient(90deg,var(--o),var(--o3),transparent)}
.od-head{display:flex;align-items:center;gap:8px;margin-bottom:11px;font-size:11px;font-weight:850;text-transform:uppercase;letter-spacing:.09em}
.od-head>svg{color:var(--o2)}
.od-head small{margin-left:auto;color:var(--faint);font-size:8.5px;font-weight:700;letter-spacing:.02em;text-transform:none}

.od-buyer{display:flex;align-items:center;justify-content:space-between;gap:10px}
.od-buyer>div{display:flex;flex-direction:column;min-width:0}
.od-buyer strong{font-size:14px;font-weight:800;letter-spacing:-.012em}
.od-buyer small{margin-top:2px;font-size:9.5px;color:var(--faint);font-family:ui-monospace,monospace}
.od-buyer a{display:flex;align-items:center;gap:6px;padding:9px 12px;border-radius:11px;color:#fff;
  background:linear-gradient(135deg,#28ae76,var(--green2));font-size:10.5px;font-weight:800;text-decoration:none;white-space:nowrap;
  box-shadow:0 8px 18px -10px rgba(15,122,76,.95);transition:transform .18s ease,box-shadow .18s ease}
.od-buyer a:hover{transform:translateY(-1px);box-shadow:0 12px 22px -10px rgba(15,122,76,1)}

.od-address{display:flex;align-items:center;gap:8px;margin-top:10px;padding:9px 10px;border:1px dashed var(--line2);border-radius:12px;
  color:var(--muted);background:rgba(247,249,252,.75);font-size:11px;line-height:1.45}
.od-address>svg{color:var(--o2);flex:none}
.od-address span{flex:1}
.od-address button{width:30px;height:30px;flex:none;display:grid;place-items:center;border:1px solid var(--line2);border-radius:9px;background:#fff;color:var(--muted)}
.od-address button:hover{color:var(--o2);border-color:rgba(249,115,22,.45)}

.od-materials{display:grid;gap:8px;margin-top:11px}
.od-material-card {
  display: grid;
  grid-template-columns:
    minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: 13px;
  background:
    linear-gradient(
      180deg,
      #fff,
      #f7f9fc
    );
  color: var(--ink);
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.od-material-card:hover {
  border-color:
    rgba(249, 115, 22, 0.42);
  background: #fff;
  transform: translateY(-1px);
  box-shadow:
    0 12px 24px -16px
      rgba(18, 28, 45, 0.7);
}

.od-material-main {
  min-width: 0;
  display: grid;
  grid-template-columns:
    52px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--ink);
  text-align: left;
}

.od-material-main > span {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.od-material-main > span b {
  overflow: hidden;
  color: var(--ink);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: -0.01em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.od-material-main > span small {
  margin-top: 2px;
  overflow: hidden;
  color: var(--faint);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.od-rate-button {
  min-height: 24px;
  max-width: 94px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 0 5px;
  border: 1px solid
    rgba(249, 115, 22, 0.2);
  border-radius: 7px;
  background: linear-gradient(
    180deg,
    #fff2e7,
    #fde8d8
  );
  color: var(--o2);
  font-size: 8.5px;
  font-weight: 850;
  line-height: 1;
  font-variant-numeric:
    tabular-nums;
  white-space: nowrap;
  box-shadow:
    0 3px 8px -8px
      rgba(194, 86, 11, 0.7);
}

.od-rate-button svg {
  transition:
    transform 0.18s ease;
}

.od-rate-button:hover {
  border-color:
    rgba(249, 115, 22, 0.48);
  background: #ffead8;
  transform: translateY(-1px);
  box-shadow:
    0 7px 14px -12px
      rgba(194, 86, 11, 0.9);
}

.od-rate-button:hover svg {
  transform: translateX(2px);
}
  .od-material-thumbnail {
    width: 52px;
    height: 42px;
    display: block;
    object-fit: cover;
    border-radius: 10px;
    background: #f4f7fb;
    box-shadow:
      0 2px 8px -3px
        rgba(18, 28, 45, 0.5),
      0 0 0 1px
        rgba(255, 255, 255, 0.35)
        inset;
  }
.od-materials>button:hover{border-color:rgba(249,115,22,.42);background:#fff;transform:translateY(-1px);box-shadow:0 12px 24px -16px rgba(18,28,45,.7)}
.od-art{position:relative;height:42px;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px -3px rgba(18,28,45,.5),0 0 0 1px rgba(255,255,255,.35) inset}
.od-art::after{content:"";position:absolute;inset:0;background:linear-gradient(160deg,rgba(255,255,255,.34),transparent 52%)}
.od-art i,.od-art b,.od-art u{position:absolute;border-radius:50%;background:rgba(255,255,255,.24)}
.od-art i{width:18px;height:18px;left:16%;top:18%}
.od-art b{width:24px;height:18px;right:12%;bottom:15%}
.od-art u{width:11px;height:11px;left:52%;top:56%;background:rgba(255,255,255,.16)}
.od-materials span{display:flex;flex-direction:column;min-width:0}
.od-materials span b{font-size:13px;font-weight:800;letter-spacing:-.01em}
.od-materials span small{margin-top:2px;font-size:10.5px;color:var(--faint)}
.od-materials>button>strong{padding:5px 9px;border-radius:9px;font-size:12px;font-weight:850;color:var(--o2);background:var(--soft);white-space:nowrap;font-variant-numeric:tabular-nums}
.od-overview-total{display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between;margin-top:11px;padding-top:10px;
  border-top:1px dashed var(--line2);font-size:10px;color:var(--muted);font-weight:600}
.od-overview-total b{color:var(--ink);font-size:12px;font-weight:850;font-variant-numeric:tabular-nums}

/* ---------- stages ---------- */
.od-stage{overflow:hidden}
.od-stage.complete{border-color:rgba(31,148,99,.28)}
.od-stage.open{box-shadow:0 3px 10px rgba(18,28,45,.06),0 26px 48px -24px rgba(18,28,45,.4)}
.od-stage.locked{opacity:.72}
.od-stage-toggle{width:100%;display:grid;grid-template-columns:30px 1fr auto;align-items:center;gap:9px;padding:13px;border:0;background:transparent;text-align:left}
.od-stage-toggle:hover{background:rgba(249,115,22,.045)}
.od-stage-icon{width:28px;height:28px;display:grid;place-items:center;border-radius:10px;color:var(--o2);
  background:var(--soft);box-shadow:0 0 0 1px rgba(249,115,22,.14) inset;transition:transform .22s ease}
.od-stage.open .od-stage-icon{transform:scale(1.05)}
.complete .od-stage-icon{color:var(--green2);background:rgba(31,148,99,.12);box-shadow:0 0 0 1px rgba(31,148,99,.2) inset}
.locked .od-stage-icon{color:var(--faint);background:#eef2f6;box-shadow:none}
.od-stage-toggle>span:nth-child(2){display:flex;flex-direction:column;min-width:0}
.od-stage-toggle b{font-size:12.5px;font-weight:800;letter-spacing:-.008em}
.od-stage-toggle small{margin-top:3px;color:var(--muted);font-size:9.5px;line-height:1.4}
.od-stage-toggle em{padding:5px 8px;border-radius:999px;color:#a15c07;background:rgba(224,139,30,.12);
  border:1px solid rgba(224,139,30,.2);font-size:8px;font-weight:850;font-style:normal;letter-spacing:.09em;white-space:nowrap}
.complete .od-stage-toggle em{color:var(--green2);background:rgba(31,148,99,.12);border-color:rgba(31,148,99,.22)}
.locked .od-stage-toggle em{color:var(--faint);background:#eef2f6;border-color:var(--line2)}
.od-stage-body{padding:13px;border-top:1px solid var(--line);background:linear-gradient(180deg,rgba(247,249,252,.6),transparent 60%);
  animation:odReveal .32s cubic-bezier(.2,.8,.3,1)}
@keyframes odReveal{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}

/* ---------- form controls ---------- */
.od-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.od-grid label,.od-form label,.od-field{display:block;color:var(--faint);font-size:8.5px;font-weight:850;letter-spacing:.1em;text-transform:uppercase}
.od-grid input,.od-form input,.od-form select,.od-field input,.od-field textarea{width:100%;height:41px;margin-top:5px;padding:0 11px;
  border:1px solid var(--line2);border-radius:11px;background:#fff;color:var(--ink);font-size:13px;font-weight:600;outline:0;
  box-shadow:var(--sh-s);transition:border-color .18s ease,box-shadow .18s ease}
.od-grid input:focus,.od-form input:focus,.od-form select:focus,.od-field input:focus,.od-field textarea:focus{border-color:var(--o);box-shadow:var(--ring)}
.od-grid input[readonly]{color:var(--muted);background:#f4f7fb;box-shadow:none}
.od-field textarea{height:76px;padding:10px 11px;line-height:1.5;resize:vertical}
.od-save{display:block;margin:12px 0 0 auto;padding:10px 16px;border:0;border-radius:11px;color:#fff;
  background:linear-gradient(135deg,var(--o3),var(--o) 45%,var(--o2));font-size:10px;font-weight:850;letter-spacing:.06em;text-transform:uppercase;
  box-shadow:0 10px 20px -10px rgba(194,86,11,.95)}
.od-save:hover{transform:translateY(-1px);box-shadow:0 14px 26px -10px rgba(194,86,11,1)}

/* ---------- loading stage ---------- */
.od-loading-summary{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:12px;border:1px solid var(--line);border-radius:14px;
  background:linear-gradient(135deg,#fff,#f5f8fc)}
.od-loading-summary>div:not(.od-bar){display:flex;flex-direction:column}
.od-loading-summary span{font-size:8.5px;color:var(--faint);font-weight:800;letter-spacing:.09em;text-transform:uppercase}
.od-loading-summary b{margin-top:3px;font-size:19px;font-weight:850;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.od-bar{position:relative;grid-column:1/-1;height:8px;border-radius:9px;background:#e5eaf0;overflow:hidden;box-shadow:0 1px 2px rgba(18,28,45,.09) inset}
.od-bar i{display:block;height:100%;border-radius:9px;background:linear-gradient(90deg,var(--o),var(--o3));
  box-shadow:0 0 12px -2px rgba(249,115,22,.85);transition:width .7s cubic-bezier(.2,.8,.3,1)}
.od-bar i::after{content:"";position:absolute;inset:0;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.55),transparent);background-size:180px 100%;animation:odSweep 2.2s linear infinite}
@keyframes odSweep{from{background-position:-180px 0}to{background-position:calc(100% + 180px) 0}}

.od-material-progress{margin-top:11px}
.od-material-progress>div{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 0;border-bottom:1px solid var(--line)}
.od-material-progress>div:last-child{border-bottom:0}
.od-material-progress span{display:flex;flex-direction:column;min-width:0}
.od-material-progress b{font-size:11px;font-weight:800}
.od-material-progress small{margin-top:2px;font-size:9px;color:var(--faint)}
.od-material-progress strong{padding:4px 9px;border-radius:999px;font-size:9px;font-weight:850;white-space:nowrap;
  color:#a15c07;background:rgba(224,139,30,.12);border:1px solid rgba(224,139,30,.2)}
.od-material-progress strong.done{color:var(--green2);background:rgba(31,148,99,.12);border-color:rgba(31,148,99,.22)}
.od-rate-sheet {
  padding-bottom: 22px;
}

.od-cost-section {
  margin-top: 13px;
  padding: 12px 13px;
  border: 1px solid var(--line);
  border-radius: 15px;
  background:
    linear-gradient(
      180deg,
      #ffffff,
      #f8fafc
    );
}

.od-cost-section h3 {
  margin: 0 0 7px;
  color: var(--o2);
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.od-cost-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 9px 0;
  border-bottom: 1px dashed
    var(--line2);
}

.od-cost-row:last-child {
  border-bottom: 0;
}

.od-cost-row span {
  color: var(--muted);
  font-size: 10.5px;
  font-weight: 600;
}

.od-cost-row b {
  color: var(--ink);
  font-size: 11px;
  font-weight: 850;
  text-align: right;
  font-variant-numeric:
    tabular-nums;
}

.od-cost-row .od-cost-empty {
  color: var(--faint);
  font-style: italic;
  font-weight: 700;
}

.od-final-rate-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-top: 14px;
  padding: 14px;
  border: 1px solid
    rgba(249, 115, 22, 0.2);
  border-radius: 15px;
  background:
    linear-gradient(
      135deg,
      #fff3e8,
      #ffead7
    );
}

.od-final-rate-card > div {
  display: flex;
  flex-direction: column;
}

.od-final-rate-card span {
  color: var(--o2);
  font-size: 11px;
  font-weight: 900;
}

.od-final-rate-card small {
  margin-top: 3px;
  color: var(--muted);
  font-size: 8.5px;
  line-height: 1.35;
}

.od-final-rate-card strong {
  color: var(--o2);
  font-size: 20px;
  font-weight: 900;
  white-space: nowrap;
  font-variant-numeric:
    tabular-nums;
}

.od-material-total-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-top: 10px;
  padding: 12px 14px;
  border: 1px solid
    rgba(31, 148, 99, 0.22);
  border-radius: 14px;
  background:
    linear-gradient(
      135deg,
      #f0fbf5,
      #e1f5ea
    );
}

.od-material-total-card span {
  color: var(--green2);
  font-size: 10.5px;
  font-weight: 800;
}

.od-material-total-card strong {
  color: var(--green2);
  font-size: 15px;
  font-weight: 900;
  font-variant-numeric:
    tabular-nums;
}

.od-vehicle-list{display:grid;gap:10px;margin-top:12px}
.od-vehicle{position:relative;padding:11px;border:1px solid var(--line);border-radius:14px;overflow:hidden;
  background:linear-gradient(180deg,#fff,#fafcfe);box-shadow:var(--sh-s);transition:transform .2s cubic-bezier(.2,.8,.3,1),box-shadow .2s ease,border-color .2s ease}
.od-vehicle::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--line2)}
.od-vehicle:hover{transform:translateY(-2px);box-shadow:0 16px 30px -20px rgba(18,28,45,.85)}
.od-vehicle.v-loaded{border-color:rgba(31,148,99,.3)}
.od-vehicle.v-loaded::before{background:linear-gradient(180deg,#34c184,var(--green))}
.od-vehicle.v-loading{border-color:rgba(224,139,30,.34)}
.od-vehicle.v-loading::before{background:linear-gradient(180deg,var(--o3),var(--o))}
.od-vehicle-head{display:flex;align-items:center;justify-content:space-between;gap:8px}
.od-vehicle-head span{display:flex;flex-direction:column;min-width:0}
.od-vehicle-head b{font-size:11px;font-weight:850;letter-spacing:.02em}
.od-vehicle-head small{margin-top:2px;font-size:9.5px;color:var(--faint);font-family:ui-monospace,monospace;letter-spacing:.03em}
.od-vehicle-head em{padding:4px 8px;border-radius:999px;color:var(--muted);background:#eef2f6;border:1px solid var(--line2);
  font-size:7.5px;font-weight:850;font-style:normal;letter-spacing:.1em;white-space:nowrap}
.v-loaded .od-vehicle-head em{color:var(--green2);background:rgba(31,148,99,.12);border-color:rgba(31,148,99,.22)}
.v-loading .od-vehicle-head em{color:#a15c07;background:rgba(224,139,30,.12);border-color:rgba(224,139,30,.22)}
.od-vehicle-info{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:9px;padding-top:9px;border-top:1px dashed var(--line2)}
.od-vehicle-info span{display:flex;flex-direction:column;min-width:0}
.od-vehicle-info b{font-size:10.5px;font-weight:800}
.od-vehicle-info small{margin-top:2px;font-size:9px;color:var(--faint);font-variant-numeric:tabular-nums}
.od-vehicle-info a{width:32px;height:32px;flex:none;display:grid;place-items:center;border-radius:10px;color:var(--green2);
  background:rgba(31,148,99,.1);border:1px solid rgba(31,148,99,.18);transition:transform .18s ease,background .18s ease}
.od-vehicle-info a:hover{transform:translateY(-1px);background:rgba(31,148,99,.16)}
.od-vehicle-meta{display:flex;align-items:center;gap:9px;margin-top:9px;padding:7px 9px;border-radius:10px;
  background:#f4f7fb;font-size:9px;color:var(--muted);font-weight:600}
.od-vehicle-meta b{margin-left:auto;color:var(--ink);font-size:10.5px;font-weight:850;font-variant-numeric:tabular-nums}
.od-vehicle-meta small{color:var(--faint)}
.od-vehicle-actions{display:flex;gap:8px;margin-top:9px}
.od-vehicle-actions button,.od-add-vehicle{display:flex;align-items:center;justify-content:center;gap:6px;min-height:34px;padding:0 11px;
  border:1px solid var(--line2);border-radius:10px;background:#fff;color:var(--ink);font-size:9px;font-weight:800;letter-spacing:.04em}
.od-vehicle-actions button{flex:1}
.od-vehicle-actions button:hover{border-color:rgba(249,115,22,.45);color:var(--o2);background:#fffaf5}
.od-add-vehicle {
  width: 100%;
  margin-top: 10px;
  min-height: 40px;
  color: var(--o2);
  border-style: dashed;
  border-color: rgba(249, 115, 22, 0.45);
  background: rgba(249, 115, 22, 0.05);
}

.od-add-vehicle:hover {
  background: rgba(249, 115, 22, 0.11);
  border-color: var(--o);
}

.od-add-another-vehicle {
  width: 100%;
  min-height: 58px;
  margin-top: 12px;
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 1px dashed
    rgba(249, 115, 22, 0.56);
  border-radius: 13px;
  background: linear-gradient(
    180deg,
    #fffaf5,
    #fff2e7
  );
  color: var(--o2);
  box-shadow:
    0 7px 18px -14px
      rgba(194, 86, 11, 0.8);
}

.od-add-another-title {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  color: var(--o2);
  font-size: 11px;
  font-weight: 850;
  letter-spacing: 0.025em;
}

.od-add-another-vehicle small {
  width: 100%;
  color: var(--muted);
  font-size: 9px;
  font-weight: 650;
  letter-spacing: 0;
  line-height: 1.3;
  text-align: center;
}

.od-add-another-vehicle:hover {
  border-color: var(--o);
  background: linear-gradient(
    180deg,
    #fff7ed,
    #ffead8
  );
  transform: translateY(-1px);
  box-shadow:
    0 13px 25px -17px
      rgba(194, 86, 11, 0.9);
}

.od-dispatch {
  width: 100%;
  margin-top: 12px;
  padding: 14px;
  border: 0;
  border-radius: 13px;
  color: #fff;
  background: linear-gradient(
    135deg,
    var(--o3),
    var(--o) 45%,
    var(--o2)
  );
  font-size: 11px;
  font-weight: 850;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  box-shadow:
    0 14px 28px -12px
      rgba(194, 86, 11, 0.95);
}
  background:linear-gradient(135deg,var(--o3),var(--o) 45%,var(--o2));font-size:11px;font-weight:850;letter-spacing:.08em;text-transform:uppercase;
  box-shadow:0 14px 28px -12px rgba(194,86,11,.95)}
.od-dispatch:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 18px 34px -12px rgba(194,86,11,1)}
.od-dispatch:disabled{color:var(--muted);background:#e8edf2;box-shadow:none}

/* ---------- transit / delivered ---------- */
.od-transit-card,.od-delivered,.od-awaiting{display:flex;align-items:center;gap:11px;padding:13px;border:1px solid var(--line);border-radius:14px;
  background:linear-gradient(135deg,#fff,#f5f8fc)}
.od-transit-card>svg{flex:none;color:var(--teal)}
.od-transit-card div,.od-delivered div,.od-awaiting span{display:flex;flex-direction:column;min-width:0}
.od-transit-card b,.od-delivered b,.od-awaiting b{font-size:11.5px;font-weight:850}
.od-transit-card small,.od-delivered small,.od-awaiting small{margin-top:3px;font-size:9.5px;color:var(--muted);line-height:1.45}
.od-route-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 0;border-bottom:1px solid var(--line)}
.od-route-row span{display:flex;flex-direction:column;min-width:0}
.od-route-row b{font-size:10.5px;font-weight:800;font-family:ui-monospace,monospace;letter-spacing:.03em}
.od-route-row small{margin-top:2px;font-size:9px;color:var(--faint)}
.od-route-row a{display:flex;align-items:center;gap:5px;padding:8px 11px;border-radius:10px;color:var(--green2);
  background:rgba(31,148,99,.1);border:1px solid rgba(31,148,99,.18);font-size:9px;font-weight:800;text-decoration:none;white-space:nowrap}
.od-route-row a:hover{background:rgba(31,148,99,.16)}
.od-awaiting{margin-top:11px;color:#a15c07;background:linear-gradient(135deg,#fffaf0,#fdf0d9);border-color:rgba(224,139,30,.26)}
.od-awaiting>svg{flex:none}
.od-delivered{color:var(--green2);background:linear-gradient(135deg,#f0fbf5,#dff4e9);border-color:rgba(31,148,99,.24)}
.od-delivered>svg{flex:none}
.od-correction{display:block;margin:11px 0 0 auto;padding:9px 13px;border:1px solid rgba(214,69,69,.32);border-radius:10px;
  color:#b42318;background:#fff;font-size:9px;font-weight:800;letter-spacing:.05em}
.od-correction:hover{background:#fff5f5;border-color:rgba(214,69,69,.55)}

/* ---------- activity ---------- */
.od-head>button{margin-left:auto;padding:7px 11px;border:1px solid rgba(224,139,30,.32);border-radius:9px;
  color:#a15c07;background:linear-gradient(180deg,#fffaf0,#fdf1dc);font-size:8.5px;font-weight:850;letter-spacing:.06em;text-transform:none}
.od-head>button:hover{border-color:rgba(224,139,30,.6);transform:translateY(-1px)}
.od-issue{display:flex;align-items:center;gap:8px;margin-bottom:6px;padding:10px;border:1px solid rgba(224,139,30,.26);border-radius:11px;
  color:#a15c07;background:linear-gradient(135deg,#fffaf0,#fdf1dc);font-size:10px;font-weight:700}
.od-issue>svg{flex:none}
.od-log{position:relative;display:flex;gap:12px;padding:9px 0 9px 2px}
.od-log::before{content:"";position:absolute;left:5px;top:0;bottom:0;width:1px;background:var(--line2)}
.od-log:first-of-type::before{top:12px}
.od-log:last-child::before{bottom:calc(100% - 12px)}
.od-log>i{position:relative;z-index:1;width:9px;height:9px;flex:none;margin-top:4px;border-radius:50%;
  background:#fff;box-shadow:0 0 0 2.5px var(--line2)}
.od-log:first-of-type>i{background:var(--o);box-shadow:0 0 0 3px var(--soft)}
.od-log span{display:flex;flex-direction:column;min-width:0}
.od-log b{font-size:10.5px;font-weight:800}
.od-log small{margin-top:2px;font-size:9px;color:var(--faint);font-variant-numeric:tabular-nums}

/* ---------- overlays, sheets, modals ---------- */
.od-overlay{position:fixed;inset:0;z-index:50;display:grid;align-items:end;background:rgba(12,22,40,.42);
  backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);animation:odFade .22s ease}
@keyframes odFade{from{opacity:0}to{opacity:1}}
.od-sheet,.od-modal{width:min(100%,560px);max-height:88vh;margin:auto;overflow-y:auto;padding:16px 16px 18px;
  border:1px solid rgba(255,255,255,.7);border-radius:24px 24px 0 0;
  background:linear-gradient(180deg,#fff,#f6f9fc);box-shadow:var(--sh-l);animation:odUp .3s cubic-bezier(.2,.8,.3,1)}
@keyframes odUp{from{opacity:0;transform:translateY(22px)}to{opacity:1;transform:none}}
.od-sheet::before{content:"";display:block;width:42px;height:4px;margin:-4px auto 12px;border-radius:9px;background:var(--line2)}
.od-modal{align-self:center;max-width:390px;border-radius:20px;padding:18px;animation:odPop .26s cubic-bezier(.2,.8,.3,1)}
@keyframes odPop{from{opacity:0;transform:scale(.95) translateY(10px)}to{opacity:1;transform:none}}
.od-sheet-head{display:flex;align-items:center;justify-content:space-between;gap:10px}
.od-sheet-head>div{display:flex;flex-direction:column;min-width:0}
.od-sheet-head b{font-size:16px;font-weight:850;letter-spacing:-.02em}
.od-sheet-head small{margin-top:2px;font-size:10px;color:var(--faint);font-family:ui-monospace,monospace}
.od-sheet-head button{width:36px;height:36px;flex:none;display:grid;place-items:center;border:1px solid var(--line2);border-radius:11px;background:#fff;color:var(--muted)}
.od-sheet-head button:hover{color:#b42318;border-color:rgba(214,69,69,.4);background:#fff6f6}

.od-form{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-top:14px}
.od-form label:first-child,.od-form label:nth-child(3){grid-column:1/-1}
.od-form label>em{display:block;margin-top:5px;color:#b42318;font-size:10px;font-style:normal;font-weight:700;letter-spacing:0;text-transform:none}
.od-form label>small{display:block;margin-top:5px;color:var(--muted);font-size:10px;font-weight:700;letter-spacing:0;text-transform:none}
.od-phone-input{height:41px;display:flex;align-items:center;margin-top:5px;border:1px solid var(--line2);border-radius:11px;
  background:#fff;overflow:hidden;box-shadow:var(--sh-s);transition:border-color .18s ease,box-shadow .18s ease}
.od-phone-input:focus-within{border-color:var(--o);box-shadow:var(--ring)}
.od-phone-input>b{padding:0 10px;color:var(--muted);font-size:12.5px;font-weight:800}
.od-phone-input>input{height:39px;margin:0;border:0;border-left:1px solid var(--line);border-radius:0;box-shadow:none}
.od-phone-input>input:focus{box-shadow:none}

.od-dual{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:15px}
.od-dual button{min-height:44px;border:1px solid var(--line2);border-radius:12px;background:#fff;
  font-size:10.5px;font-weight:850;letter-spacing:.05em;box-shadow:var(--sh-s)}
.od-dual button:hover{border-color:var(--faint)}
.od-primary{border:0!important;color:#fff!important;background:linear-gradient(135deg,var(--o3),var(--o) 45%,var(--o2))!important;
  box-shadow:0 12px 24px -12px rgba(194,86,11,.95)!important}
.od-primary:hover:not(:disabled){transform:translateY(-1px)}
.od-primary:disabled{opacity:.45}
.od-danger{border:0!important;color:#fff!important;background:linear-gradient(135deg,#ef6468,#c9363d)!important;
  box-shadow:0 12px 24px -12px rgba(201,54,61,.9)!important}
.od-modal h3{margin:0 0 7px;font-size:15.5px;font-weight:850;letter-spacing:-.02em}
.od-modal>p{margin:0 0 12px;color:var(--muted);font-size:10.5px;line-height:1.55}
.od-status-options{display:grid}
.od-status-options label{display:flex;align-items:center;gap:9px;padding:10px 2px;border-bottom:1px solid var(--line);
  font-size:10.5px;font-weight:700;cursor:pointer;transition:color .16s ease}
.od-status-options label:last-child{border-bottom:0}
.od-status-options label:hover{color:var(--o2)}
.od-status-options input{width:16px;height:16px;accent-color:var(--o);cursor:pointer}
.od-confirm{text-align:center;padding:24px 20px}
.od-confirm>span{width:52px;height:52px;display:grid;place-items:center;margin:auto;border-radius:16px;color:var(--teal);
  background:linear-gradient(135deg,#eafbf8,#d6f3ee);box-shadow:0 10px 22px -12px rgba(13,148,136,.8)}
.od-confirm h3{margin-top:13px}

/* ---------- material detail sheet ---------- */
.od-material-large{height:230px;margin-top:14px}
.od-material-large .od-art{height:100%;border-radius:16px;box-shadow:0 18px 34px -20px rgba(18,28,45,.9),0 0 0 1px rgba(255,255,255,.35) inset}
.od-material-large .od-art i{width:74px;height:74px}
.od-material-large .od-art b{width:100px;height:74px}
.od-material-large .od-art u{width:38px;height:38px}
.od-material-sheet dl{margin:14px 0 0;padding:4px 12px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.75)}
.od-material-sheet dl div{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--line);font-size:11.5px}
.od-material-sheet dl div:last-child{border-bottom:0}
.od-material-sheet dt{color:var(--muted);font-weight:600}
.od-material-sheet dd{margin:0;font-weight:800;text-align:right;font-variant-numeric:tabular-nums}
.od-material-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}
.od-material-actions button,.od-material-actions a{min-height:46px;display:flex;align-items:center;justify-content:center;gap:7px;
  border-radius:12px;font-size:11px;font-weight:850;letter-spacing:.04em;text-decoration:none;cursor:pointer}
.od-material-actions button{border:1px solid var(--line2);color:var(--ink);background:#fff;box-shadow:var(--sh-s)}
.od-material-actions button:hover{border-color:rgba(249,115,22,.45);color:var(--o2);background:#fffaf5}
.od-material-actions a{border:0;color:#fff;background:linear-gradient(135deg,#28ae76,var(--green2));box-shadow:0 12px 24px -12px rgba(15,122,76,.95)}
.od-material-actions a:hover{transform:translateY(-1px)}

.od-toast{position:fixed;z-index:80;left:50%;bottom:22px;transform:translate(-50%,12px) scale(.97);opacity:0;
  padding:11px 16px;border-radius:12px;color:#fff;background:linear-gradient(135deg,#1d2634,#11161f);
  border:1px solid rgba(255,255,255,.1);font-size:11px;font-weight:700;letter-spacing:.02em;pointer-events:none;
  box-shadow:0 18px 38px -14px rgba(0,0,0,.7);transition:.26s cubic-bezier(.2,.8,.3,1)}
.od-toast.show{opacity:1;transform:translate(-50%,0) scale(1)}

@media(min-width:720px){
  .od-main{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:start}
  .od-progress,.od-stages,.od-activity{grid-column:1/-1}
  .od-panel,.od-stage{margin-bottom:0}
  .od-stages>.od-stage{margin-bottom:12px}
  .od-stages>.od-stage:last-child{margin-bottom:0}
  .od-vehicle-list{grid-template-columns:1fr 1fr}
  .od-header h1{font-size:33px}
}
@media(max-width:390px){
  .od-grid,.od-form{grid-template-columns:1fr}
  .od-form label:first-child,.od-form label:nth-child(3){grid-column:auto}
  .od-materials>button{grid-template-columns:46px 1fr}
  .od-materials>button>strong{grid-column:2;justify-self:start}
  .od-vehicle-meta{flex-wrap:wrap}
  .od-vehicle-meta b{margin-left:0}
  .od-step small{font-size:7px}
  .od-header h1{font-size:25px}
}
@media(prefers-reduced-motion:reduce){
  .od-root *{transition:none!important;animation:none!important}
}
`;
