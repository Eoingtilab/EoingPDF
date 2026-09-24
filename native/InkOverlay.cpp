// Owned, non-activating layered window. All calls run on the owner's UI thread.
#define NOMINMAX
#include <windows.h>
#include <windowsx.h>
#include <d2d1.h>
#include <wrl/client.h>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <new>
#include <vector>
#include <memory>
#include "GpuInkSurface.h"
using Microsoft::WRL::ComPtr;
using InputCallback = void(__stdcall*)(UINT, int, int);
struct InkStyle { float red, green, blue, alpha, width; UINT fill; };

struct Overlay {
    HWND window = nullptr;
    DWORD thread = GetCurrentThreadId();
    HDC dc = nullptr;
    HBITMAP bitmap = nullptr;
    HGDIOBJ original = nullptr;
    void* pixels = nullptr;
    int width = 0, height = 0;
    bool capture = false;
    bool frameValid = false, previousCapture = false;
    float previousPen = 0;
    std::vector<D2D1_POINT_2F> previousPoints;
    std::vector<UINT> previousEnds;
    std::vector<InkStyle> previousStyles;
    InputCallback input = nullptr;
    ComPtr<ID2D1Factory> factory;
    ComPtr<ID2D1DCRenderTarget> target;
    std::unique_ptr<GpuInkSurface> gpu;

    ~Overlay() {
        input = nullptr;
        gpu.reset();
        if (window) DestroyWindow(window);
        target.Reset();
        if (original) SelectObject(dc, original);
        if (bitmap) DeleteObject(bitmap);
        if (dc) DeleteDC(dc);
    }

    HRESULT resize(int x, int y, int w, int h) {
        if (w <= 0 || h <= 0 || uint64_t(w) * h > 16777216) return E_INVALIDARG;
        if (gpu) {
            HRESULT hr = gpu->resize(w, h);
            if (FAILED(hr)) return hr;
            if (w != width || h != height) frameValid = false;
            width = w; height = h;
            return SetWindowPos(window, nullptr, x, y, w, h, SWP_NOACTIVATE | SWP_NOZORDER) ? S_OK : E_FAIL;
        }
        if (w != width || h != height) {
            BITMAPINFO info{};
            info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
            info.bmiHeader.biWidth = w;
            info.bmiHeader.biHeight = -h;
            info.bmiHeader.biPlanes = 1;
            info.bmiHeader.biBitCount = 32;
            info.bmiHeader.biCompression = BI_RGB;
            void* buffer = nullptr;
            HBITMAP next = CreateDIBSection(dc, &info, DIB_RGB_COLORS, &buffer, nullptr, 0);
            if (!next) return E_OUTOFMEMORY;
            HGDIOBJ previous = SelectObject(dc, next);
            if (!previous || previous == HGDI_ERROR) { DeleteObject(next); return E_FAIL; }
            if (!original) original = previous;
            if (bitmap) DeleteObject(bitmap);
            bitmap = next; pixels = buffer; width = w; height = h;
            frameValid = false;
            std::memset(pixels, 0, size_t(w) * h * 4);
        }
        if (!SetWindowPos(window, nullptr, x, y, w, h, SWP_NOACTIVATE | SWP_NOZORDER)) return E_FAIL;
        return S_OK;
    }

    HRESULT render(const D2D1_POINT_2F* points, UINT count, const UINT* ends, UINT strokes, float pen,
                   const InkStyle* styles = nullptr) {
        if (width <= 0 || height <= 0 || (count && !points) || (strokes && !ends) ||
            count > 250000 || strokes > 10000 || !std::isfinite(pen) || pen <= 0 || pen > 1000)
            return E_INVALIDARG;
        UINT start = 0;
        for (UINT s = 0; s < strokes; ++s) {
            if (ends[s] <= start || ends[s] > count) return E_INVALIDARG;
            start = ends[s];
        }
        if (start != count) return E_INVALIDARG;
        std::vector<InkStyle> currentStyles(strokes, {1.f, .82f, 0.f, .9f, pen, 0});
        for (UINT s = 0; s < strokes; ++s) {
            if (styles) currentStyles[s] = styles[s];
            const auto& style = currentStyles[s];
            if (!std::isfinite(style.red) || style.red < 0 || style.red > 1 ||
                !std::isfinite(style.green) || style.green < 0 || style.green > 1 ||
                !std::isfinite(style.blue) || style.blue < 0 || style.blue > 1 ||
                !std::isfinite(style.alpha) || style.alpha < 0 || style.alpha > 1 ||
                !std::isfinite(style.width) || style.width <= 0 || style.width > 1000 || style.fill > 1)
                return E_INVALIDARG;
        }
        for (UINT i = 0; i < count; ++i)
            if (!std::isfinite(points[i].x) || !std::isfinite(points[i].y) ||
                points[i].x < 0 || points[i].x > 1 || points[i].y < 0 || points[i].y > 1)
                return E_INVALIDARG;
        if (frameValid && previousPen == pen && previousCapture == capture) {
            if (count == previousPoints.size() && strokes == previousEnds.size() &&
                (!count || std::memcmp(points, previousPoints.data(), count * sizeof(*points)) == 0) &&
                (!strokes || (std::memcmp(ends, previousEnds.data(), strokes * sizeof(*ends)) == 0 &&
                 previousStyles.size() == strokes &&
                 std::memcmp(currentStyles.data(), previousStyles.data(), strokes * sizeof(InkStyle)) == 0)))
                return S_FALSE; // Identical frame: neither rasterize nor submit it.
        }
        frameValid = false;
        if (!gpu && !target) {
            auto properties = D2D1::RenderTargetProperties(D2D1_RENDER_TARGET_TYPE_DEFAULT,
                D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM, D2D1_ALPHA_MODE_PREMULTIPLIED), 96, 96);
            HRESULT hr = factory->CreateDCRenderTarget(&properties, &target);
            if (FAILED(hr)) return hr;
        }
        ComPtr<ID2D1RenderTarget> renderer;
        HRESULT hr;
        if (gpu) hr = gpu->drawing.As(&renderer);
        else {
            RECT whole{0, 0, width, height};
            hr = target->BindDC(dc, &whole);
            if (SUCCEEDED(hr)) hr = target.As(&renderer);
        }
        if (FAILED(hr)) return hr;
        std::vector<ComPtr<ID2D1SolidColorBrush>> brushes(strokes);
        for (UINT s = 0; s < strokes; ++s) {
            const auto& color = currentStyles[s];
            hr = renderer->CreateSolidColorBrush(D2D1::ColorF(color.red, color.green, color.blue, color.alpha), &brushes[s]);
            if (FAILED(hr)) return hr;
        }
        ComPtr<ID2D1StrokeStyle> style;
        auto properties = D2D1::StrokeStyleProperties();
        properties.startCap = properties.endCap = properties.dashCap = D2D1_CAP_STYLE_ROUND;
        properties.lineJoin = D2D1_LINE_JOIN_ROUND;
        hr = factory->CreateStrokeStyle(properties, nullptr, 0, &style);
        if (FAILED(hr)) return hr;
        std::vector<ComPtr<ID2D1PathGeometry>> geometries;
        geometries.reserve(strokes);
        start = 0;
        for (UINT s = 0; s < strokes; ++s) {
            ComPtr<ID2D1PathGeometry> geometry;
            ComPtr<ID2D1GeometrySink> sink;
            hr = factory->CreatePathGeometry(&geometry);
            if (SUCCEEDED(hr)) hr = geometry->Open(&sink);
            if (FAILED(hr)) return hr;
            sink->BeginFigure(D2D1::Point2F(points[start].x * width, points[start].y * height),
                              currentStyles[s].fill ? D2D1_FIGURE_BEGIN_FILLED : D2D1_FIGURE_BEGIN_HOLLOW);
            for (UINT i = start + 1; i < ends[s]; ++i) {
                sink->AddLine(D2D1::Point2F(points[i].x * width, points[i].y * height));
            }
            sink->EndFigure(currentStyles[s].fill ? D2D1_FIGURE_END_CLOSED : D2D1_FIGURE_END_OPEN);
            hr = sink->Close();
            if (FAILED(hr)) return hr;
            geometries.push_back(geometry);
            start = ends[s];
        }
        renderer->BeginDraw();
        renderer->SetTransform(D2D1::Matrix3x2F::Identity());
        renderer->Clear(D2D1::ColorF(0.f, 0.f, 0.f, capture ? 1.f / 255 : 0.f));
        for (UINT s = 0; s < strokes; ++s) {
            if (currentStyles[s].fill) renderer->FillGeometry(geometries[s].Get(), brushes[s].Get());
            else renderer->DrawGeometry(geometries[s].Get(), brushes[s].Get(), currentStyles[s].width, style.Get());
        }
        hr = renderer->EndDraw();
        if (hr == D2DERR_RECREATE_TARGET) target.Reset();
        if (FAILED(hr)) return hr;
        if (gpu) {
            hr = gpu->present();
            if (FAILED(hr)) return hr;
        } else {
            SIZE size{width, height}; POINT origin{0, 0};
            BLENDFUNCTION blend{AC_SRC_OVER, 0, 255, AC_SRC_ALPHA};
            if (!UpdateLayeredWindow(window, nullptr, nullptr, &size, dc, &origin, 0, &blend, ULW_ALPHA))
                return E_FAIL;
        }
        if (count) previousPoints.assign(points, points + count); else previousPoints.clear();
        if (strokes) previousEnds.assign(ends, ends + strokes); else previousEnds.clear();
        previousStyles = std::move(currentStyles);
        previousPen = pen; previousCapture = capture; frameValid = true;
        return S_OK;
    }
};

static LRESULT CALLBACK WindowProc(HWND window, UINT message, WPARAM w, LPARAM l) {
    Overlay* overlay = reinterpret_cast<Overlay*>(GetWindowLongPtrW(window, GWLP_USERDATA));
    if (message == WM_NCCREATE) {
        overlay = static_cast<Overlay*>(reinterpret_cast<CREATESTRUCTW*>(l)->lpCreateParams);
        SetWindowLongPtrW(window, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(overlay));
    }
    if (message == WM_MOUSEACTIVATE) return MA_NOACTIVATE;
    if (overlay && message == WM_NCHITTEST) return overlay->capture ? HTCLIENT : HTTRANSPARENT;
    if (overlay && message == WM_CAPTURECHANGED && overlay->input)
        overlay->input(message, 0, 0);
    if (overlay && message == WM_CANCELMODE && GetCapture() == window)
        ReleaseCapture();
    if (overlay && overlay->capture) {
        if (message == WM_LBUTTONDOWN) SetCapture(window);
        if (overlay->input && (message == WM_LBUTTONDOWN || message == WM_MOUSEMOVE ||
                              message == WM_LBUTTONUP || message == WM_RBUTTONDOWN || message == WM_LBUTTONDBLCLK))
            overlay->input(message, GET_X_LPARAM(l), GET_Y_LPARAM(l));
        if (message == WM_LBUTTONUP && GetCapture() == window) ReleaseCapture();
        if (message == WM_LBUTTONDOWN || message == WM_LBUTTONUP || message == WM_MOUSEMOVE || message == WM_RBUTTONDOWN || message == WM_LBUTTONDBLCLK)
            return 0;
    }
    return DefWindowProcW(window, message, w, l);
}

#define API extern "C" __declspec(dllexport)
static Overlay* createOverlay(HWND owner, InputCallback input, int backend) noexcept {
    if (backend < 0 || backend > 2) return nullptr;
    auto overlay = new (std::nothrow) Overlay;
    if (!overlay) return nullptr;
    WNDCLASSW wc{};
    wc.style = CS_DBLCLKS;
    wc.lpfnWndProc = WindowProc; wc.hInstance = GetModuleHandleW(nullptr);
    wc.lpszClassName = L"EoingPDF.Direct2D.Ink";
    wc.hCursor = LoadCursor(nullptr, IDC_CROSS);
    if (!RegisterClassW(&wc) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) { delete overlay; return nullptr; }
    if (FAILED(D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED, overlay->factory.GetAddressOf()))) {
        delete overlay; return nullptr;
    }
    overlay->dc = CreateCompatibleDC(nullptr);
    if (!overlay->dc) { delete overlay; return nullptr; }
    overlay->input = input;
    const DWORD material = backend == 1 ? WS_EX_LAYERED : WS_EX_NOREDIRECTIONBITMAP;
    overlay->window = CreateWindowExW(material | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
        wc.lpszClassName, L"어잉PDF 판서", WS_POPUP, 0, 0, 1, 1, owner, nullptr, wc.hInstance, overlay);
    if (!overlay->window) { delete overlay; return nullptr; }
    if (backend != 1) {
        overlay->gpu.reset(new (std::nothrow) GpuInkSurface);
        if (!overlay->gpu || FAILED(overlay->gpu->initialize(overlay->window))) {
            overlay->gpu.reset();
            if (backend == 2) { delete overlay; return nullptr; }
            LONG_PTR style = GetWindowLongPtrW(overlay->window, GWL_EXSTYLE);
            SetWindowLongPtrW(overlay->window, GWL_EXSTYLE, (style & ~WS_EX_NOREDIRECTIONBITMAP) | WS_EX_LAYERED);
        } else {
            overlay->gpu->factory.As(&overlay->factory);
        }
    }
    return overlay;
}
API Overlay* __stdcall InkCreate(HWND owner, InputCallback input) noexcept { return createOverlay(owner, input, 0); }
API Overlay* __stdcall InkCreateWithBackend(HWND owner, InputCallback input, int backend) noexcept {
    return createOverlay(owner, input, backend);
}
API int __stdcall InkBackend(Overlay* overlay) noexcept { return overlay && overlay->gpu ? 2 : 1; }
API HRESULT __stdcall InkWait(Overlay* overlay) noexcept {
    if (!overlay || overlay->thread != GetCurrentThreadId()) return E_INVALIDARG;
    return overlay->gpu ? overlay->gpu->wait() : S_OK;
}
API void __stdcall InkDestroy(Overlay* overlay) noexcept {
    if (overlay && overlay->thread == GetCurrentThreadId()) delete overlay;
}
API HRESULT __stdcall InkResize(Overlay* overlay, int x, int y, int w, int h) noexcept {
    if (!overlay || overlay->thread != GetCurrentThreadId()) return E_INVALIDARG;
    return overlay->resize(x, y, w, h);
}
API HRESULT __stdcall InkRender(Overlay* overlay, const D2D1_POINT_2F* points, UINT count,
                                const UINT* ends, UINT strokes, float pen) noexcept {
    if (!overlay || overlay->thread != GetCurrentThreadId()) return E_INVALIDARG;
    try { return overlay->render(points, count, ends, strokes, pen); }
    catch (const std::bad_alloc&) { overlay->frameValid = false; return E_OUTOFMEMORY; }
    catch (...) { overlay->frameValid = false; return E_FAIL; }
}
API HRESULT __stdcall InkRenderStyled(Overlay* overlay, const D2D1_POINT_2F* points, UINT count,
                                      const UINT* ends, UINT strokes, float pen, const InkStyle* styles) noexcept {
    if (!overlay || overlay->thread != GetCurrentThreadId() || (strokes && !styles)) return E_INVALIDARG;
    try { return overlay->render(points, count, ends, strokes, pen, styles); }
    catch (const std::bad_alloc&) { overlay->frameValid = false; return E_OUTOFMEMORY; }
    catch (...) { overlay->frameValid = false; return E_FAIL; }
}
API void __stdcall InkMode(Overlay* overlay, BOOL capture) noexcept {
    if (!overlay || overlay->thread != GetCurrentThreadId()) return;
    overlay->capture = !!capture;
    LONG_PTR style = GetWindowLongPtrW(overlay->window, GWL_EXSTYLE);
    SetWindowLongPtrW(overlay->window, GWL_EXSTYLE, capture ? style & ~WS_EX_TRANSPARENT : style | WS_EX_TRANSPARENT);
    if (!capture && GetCapture() == overlay->window) ReleaseCapture();
}
API void __stdcall InkShow(Overlay* overlay, BOOL visible) noexcept {
    if (overlay && overlay->thread == GetCurrentThreadId()) ShowWindow(overlay->window, visible ? SW_SHOWNOACTIVATE : SW_HIDE);
}
API HWND __stdcall InkWindow(Overlay* overlay) noexcept { return overlay ? overlay->window : nullptr; }
API HRESULT __stdcall InkCopyPixels(Overlay* overlay, void* destination, size_t bytes) noexcept {
    if (overlay && overlay->thread == GetCurrentThreadId() && overlay->gpu)
        return overlay->gpu->copyPixels(destination, bytes);
    if (!overlay || overlay->thread != GetCurrentThreadId() || !destination || !overlay->pixels ||
        bytes != size_t(overlay->width) * overlay->height * 4) return E_INVALIDARG;
    GdiFlush();
    std::memcpy(destination, overlay->pixels, bytes);
    return S_OK;
}
