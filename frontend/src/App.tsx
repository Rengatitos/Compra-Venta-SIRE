import { lazy } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';

import { AppShell } from '@/components/layout/AppShell';
import { ToastProvider } from '@/components/ui/ToastProvider';
import { AuthProvider } from '@/features/auth/AuthProvider';
import { LoginPage } from '@/features/auth/LoginPage';
import { ProtectedRoute } from '@/features/auth/ProtectedRoute';
import { RegistroPage } from '@/features/auth/RegistroPage';
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
const ComprobanteDetallePage = lazy(() =>
  import('@/features/comprobantes/ComprobanteDetallePage').then((m) => ({
    default: m.ComprobanteDetallePage,
  })),
);
const AnalisisPage = lazy(() =>
  import('@/features/analisis/AnalisisPage').then((m) => ({ default: m.AnalisisPage })),
);
const DetallePage = lazy(() =>
  import('@/features/detalle/DetallePage').then((m) => ({ default: m.DetallePage })),
);
const ReferenciasPage = lazy(() =>
  import('@/features/referencias/ReferenciasPage').then((m) => ({
    default: m.ReferenciasPage,
  })),
);
const AjustesPage = lazy(() =>
  import('@/features/empresa/AjustesPage').then((m) => ({ default: m.AjustesPage })),
);

export function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/registro" element={<RegistroPage />} />

            <Route element={<ProtectedRoute />}>
              <Route element={<AppShell />}>
                <Route index element={<DashboardPage />} />
                <Route path="periodos" element={<PeriodosPage />} />
                <Route path="periodos/:periodo" element={<ComprobantesPage />} />
                <Route
                  path="periodos/:periodo/comprobantes/:serieNumero"
                  element={<ComprobanteDetallePage />}
                />
                <Route path="periodos/:periodo/analisis" element={<AnalisisPage />} />
                <Route path="periodos/:periodo/detalle" element={<DetallePage />} />
                <Route path="referencias" element={<ReferenciasPage />} />
                <Route path="ajustes" element={<AjustesPage />} />
                <Route path="*" element={<NoEncontradaPage />} />
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
