import { lazy } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router';

import { AppShell } from '@/components/layout/AppShell';
import { ToastProvider } from '@/components/ui/ToastProvider';
import { AuthProvider } from '@/features/auth/AuthProvider';
import { LoginPage } from '@/features/auth/LoginPage';
import { ProtectedRoute } from '@/features/auth/ProtectedRoute';
import { EmpresaGate } from '@/features/empresas/EmpresaGate';
import { NoEncontradaPage } from '@/features/shared/NoEncontradaPage';

/**
 * Las pantallas autenticadas se cargan a demanda. Importa sobre todo por el
 * dashboard: arrastra la librería de gráficos, que es la dependencia más pesada
 * del proyecto y no hace falta para iniciar sesión. AppShell envuelve el
 * `<Outlet>` en un Suspense, así que el armazón nunca desaparece al navegar.
 */
const DashboardPage = lazy(() =>
  import('@/features/dashboard/DashboardPage').then((m) => ({ default: m.DashboardPage })),
);
const PeriodosPage = lazy(() =>
  import('@/features/periodos/PeriodosPage').then((m) => ({ default: m.PeriodosPage })),
);
const ComprobantesPage = lazy(() =>
  import('@/features/comprobantes/ComprobantesPage').then((m) => ({
    default: m.ComprobantesPage,
  })),
);
const ProcesosPage = lazy(() =>
  import('@/features/procesos/ProcesosPage').then((m) => ({ default: m.ProcesosPage })),
);
const AjustesPage = lazy(() =>
  import('@/features/empresa/AjustesPage').then((m) => ({ default: m.AjustesPage })),
);
const PlanCuentasPage = lazy(() =>
  import('@/features/plan-cuentas/PlanCuentasPage').then((m) => ({
    default: m.PlanCuentasPage,
  })),
);
const AuditoriaPage = lazy(() =>
  import('@/features/auditoria/AuditoriaPage').then((m) => ({ default: m.AuditoriaPage })),
);
const ReportePage = lazy(() =>
  import('@/features/reporte/ReportePage').then((m) => ({ default: m.ReportePage })),
);
const ExternosPage = lazy(() =>
  import('@/features/externos/ExternosPage').then((m) => ({ default: m.ExternosPage })),
);
const NuevaEmpresaPage = lazy(() =>
  import('@/features/empresas/NuevaEmpresaPage').then((m) => ({ default: m.NuevaEmpresaPage })),
);

export function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            {/* El alta dejó de ser pública al dejar de ser la puerta de entrada.
                La redirección es por cortesía con los enlaces antiguos. */}
            <Route path="/registro" element={<Navigate to="/empresas/nueva" replace />} />

            <Route element={<ProtectedRoute />}>
              {/* Fuera del armazón: la barra anuncia la empresa activa, que no
                  es la que se está registrando, y la navegación lateral no
                  tiene ninguna sección para esta pantalla. */}
              <Route path="empresas/nueva" element={<NuevaEmpresaPage />} />

              {/* ProtectedRoute exige sesión; EmpresaGate, empresa activa.
                  AppShell da por hecha la segunda, así que va dentro. */}
              <Route element={<EmpresaGate />}>
                <Route element={<AppShell />}>
                  <Route index element={<DashboardPage />} />
                  <Route path="periodos" element={<PeriodosPage />} />
                  <Route path="periodos/:periodo" element={<ComprobantesPage />} />
                  <Route path="periodos/:periodo/auditoria" element={<AuditoriaPage />} />
                  <Route path="periodos/:periodo/reporte" element={<ReportePage />} />
                  <Route path="externos" element={<ExternosPage />} />
                  <Route path="procesos" element={<ProcesosPage />} />
                  <Route path="plan-cuentas" element={<PlanCuentasPage />} />
                  <Route path="ajustes" element={<AjustesPage />} />
                  <Route path="*" element={<NoEncontradaPage />} />
                </Route>
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
