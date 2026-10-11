import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../auth/AuthContext.jsx";
import LoginScreen from "../components/LoginScreen.jsx";

// The whole auth API surface is mocked; the provider and screen under test
// are real. hoisted() keeps the spies reachable inside vi.mock().
const authApi = vi.hoisted(() => ({
  config: vi.fn(),
  register: vi.fn(),
  login: vi.fn(),
  google: vi.fn(),
  guest: vi.fn(),
  me: vi.fn(),
  saveGame: vi.fn(),
  listGames: vi.fn(),
}));

vi.mock("../api/authClient.js", () => ({
  authApi,
  getToken: () => null,
  setToken: () => {},
  clearToken: () => {},
  AuthError: class AuthError extends Error {},
}));

function renderLogin() {
  return render(
    <AuthProvider>
      <LoginScreen />
    </AuthProvider>,
  );
}

describe("LoginScreen", () => {
  beforeEach(() => {
    authApi.config.mockResolvedValue({ google_enabled: false, google_client_id: null });
    authApi.guest.mockResolvedValue({ token: "g", user: { id: "1", provider: "guest" } });
    authApi.login.mockResolvedValue({ token: "l", user: { id: "2", provider: "email" } });
    authApi.register.mockResolvedValue({ token: "r", user: { id: "3", provider: "email" } });
  });

  it("shows the sign-in form, the guest button and the Google note", async () => {
    renderLogin();

    expect(await screen.findByRole("button", { name: "Sign in" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Play as guest" })).toBeTruthy();
    expect(screen.getByText(/GOOGLE_CLIENT_ID is configured/)).toBeTruthy();
  });

  it("signs in as guest when the guest button is clicked", async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.click(await screen.findByRole("button", { name: "Play as guest" }));

    await waitFor(() => expect(authApi.guest).toHaveBeenCalledTimes(1));
    expect(authApi.guest).toHaveBeenCalledWith({});
  });

  it("submits email + password to the login API", async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.type(await screen.findByLabelText("Email"), "mia@example.com");
    await user.type(screen.getByLabelText("Password"), "castlerook1");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(authApi.login).toHaveBeenCalledTimes(1));
    expect(authApi.login).toHaveBeenCalledWith({
      email: "mia@example.com",
      password: "castlerook1",
    });
  });

  it("switches to the registration form and sends name + password", async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.click(await screen.findByRole("button", { name: /Create an account/ }));
    await user.type(screen.getByLabelText("Display name"), "Mia");
    await user.type(screen.getByLabelText("Email"), "mia@example.com");
    await user.type(screen.getByLabelText("Password"), "castlerook1");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(authApi.register).toHaveBeenCalledTimes(1));
    expect(authApi.register).toHaveBeenCalledWith({
      email: "mia@example.com",
      name: "Mia",
      password: "castlerook1",
    });
  });

  it("shows the server error when sign-in fails", async () => {
    authApi.login.mockRejectedValueOnce(new Error("Incorrect email or password."));
    const user = userEvent.setup();
    renderLogin();

    await user.type(await screen.findByLabelText("Email"), "mia@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Incorrect email or password.");
  });
});
