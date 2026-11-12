import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Navbar from './components/Navbar';
import Footer from './components/Footer';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import VerifyEmail from './pages/VerifyEmail';
import Inbox from './pages/Inbox';
import BorrowRequestDetail from './pages/BorrowRequestDetail';
import MyBorrowRequests from './pages/MyBorrowRequests';
import Browse from './pages/Browse';
import CreateListing from './pages/CreateListing';
import CreateBorrowRequest from './pages/CreateBorrowRequest';
import ListingDetail from './pages/ListingDetail';
import MyListings from './pages/MyListings';
import Chat from './pages/Chat';
import PaymentReviewQueue from './components/PaymentReviewQueue';

const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return <div style={{ color: 'white', padding: '100px', textAlign: 'center' }}>Loading...</div>;
  if (!isAuthenticated) return <Navigate to="/login" />;
  return children;
};

const MainLayout = ({ children }) => {
  return (
    <>
      <Navbar />
      <main style={{ paddingTop: 'var(--nav, 72px)', minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        {children}
      </main>
      <Footer />
    </>
  );
};

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <MainLayout>
          <Routes>
            <Route path="/payment-review" element={<ProtectedRoute><PaymentReviewQueue /></ProtectedRoute>} />
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/verify-email" element={<VerifyEmail />} />
            <Route path="/borrow-requests/:id" element={<BorrowRequestDetail />} />
            <Route path="/browse" element={<Browse />} />
            <Route path="/listing/:id" element={<ListingDetail />} />
            <Route path="/create-listing" element={
              <ProtectedRoute>
                <CreateListing />
              </ProtectedRoute>
            } />
            <Route path="/create-request" element={
              <ProtectedRoute>
                <CreateBorrowRequest />
              </ProtectedRoute>
            } />
            <Route path="/my-listings" element={
              <ProtectedRoute>
                <MyListings />
              </ProtectedRoute>
            } />
            <Route path="/my-borrow-requests" element={
              <ProtectedRoute>
                <MyBorrowRequests />
              </ProtectedRoute>
            } />
            <Route path="/messages" element={
              <ProtectedRoute>
                <Chat />
              </ProtectedRoute>
            } />
            <Route path="/inbox" element={
              <ProtectedRoute>
                <Inbox />
              </ProtectedRoute>
            } />
            <Route path="/messages/:conversationId" element={
              <ProtectedRoute>
                <Chat />
              </ProtectedRoute>
            } />
          </Routes>
        </MainLayout>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
