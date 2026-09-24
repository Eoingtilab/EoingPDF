#pragma once
#include <d3d11.h>
#include <dxgi1_2.h>
#include <d2d1_1.h>
#include <dcomp.h>
#include <wrl/client.h>
#include <cstring>
using Microsoft::WRL::ComPtr;

// An explicit GPU texture retains the last frame for deterministic readback.
// Presentation copies it on the GPU; CPU readback occurs only when requested.
struct GpuInkSurface {
    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11DeviceContext> commands;
    ComPtr<IDXGIFactory2> dxgi;
    ComPtr<ID2D1Factory1> factory;
    ComPtr<ID2D1Device> drawingDevice;
    ComPtr<ID2D1DeviceContext> drawing;
    ComPtr<IDCompositionDevice> composition;
    ComPtr<IDCompositionTarget> destination;
    ComPtr<IDCompositionVisual> visual;
    ComPtr<IDXGISwapChain1> swapChain;
    ComPtr<ID3D11Texture2D> texture;
    ComPtr<ID2D1Bitmap1> bitmap;
    ComPtr<ID3D11Query> fence;
    UINT width = 0, height = 0;

    HRESULT initialize(HWND window) {
        HRESULT hr = D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr,
            D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0, D3D11_SDK_VERSION,
            &device, nullptr, &commands);
        if (FAILED(hr)) return hr;
        ComPtr<IDXGIDevice> dxgiDevice;
        ComPtr<IDXGIAdapter> adapter;
        hr = device.As(&dxgiDevice);
        if (SUCCEEDED(hr)) hr = dxgiDevice->GetAdapter(&adapter);
        if (SUCCEEDED(hr)) hr = adapter->GetParent(IID_PPV_ARGS(&dxgi));
        if (FAILED(hr)) return hr;
        D2D1_FACTORY_OPTIONS options{};
        hr = D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED, __uuidof(ID2D1Factory1),
                              &options, reinterpret_cast<void**>(factory.GetAddressOf()));
        if (SUCCEEDED(hr)) hr = factory->CreateDevice(dxgiDevice.Get(), &drawingDevice);
        if (SUCCEEDED(hr)) hr = drawingDevice->CreateDeviceContext(D2D1_DEVICE_CONTEXT_OPTIONS_NONE, &drawing);
        if (SUCCEEDED(hr)) hr = DCompositionCreateDevice(dxgiDevice.Get(), IID_PPV_ARGS(&composition));
        if (SUCCEEDED(hr)) hr = composition->CreateTargetForHwnd(window, TRUE, &destination);
        if (SUCCEEDED(hr)) hr = composition->CreateVisual(&visual);
        if (SUCCEEDED(hr)) hr = destination->SetRoot(visual.Get());
        if (FAILED(hr)) return hr;
        drawing->SetDpi(96, 96);
        ComPtr<IDXGIDevice1> latency;
        if (SUCCEEDED(dxgiDevice.As(&latency))) latency->SetMaximumFrameLatency(1);
        D3D11_QUERY_DESC query{D3D11_QUERY_EVENT, 0};
        return device->CreateQuery(&query, &fence);
    }

    HRESULT resize(UINT w, UINT h) {
        if (width == w && height == h && texture) return S_OK;
        D3D11_TEXTURE2D_DESC description{};
        description.Width = w; description.Height = h;
        description.MipLevels = description.ArraySize = 1;
        description.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
        description.SampleDesc.Count = 1;
        description.Usage = D3D11_USAGE_DEFAULT;
        description.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;
        ComPtr<ID3D11Texture2D> nextTexture;
        HRESULT hr = device->CreateTexture2D(&description, nullptr, &nextTexture);
        ComPtr<IDXGISurface> surface;
        if (SUCCEEDED(hr)) hr = nextTexture.As(&surface);
        ComPtr<ID2D1Bitmap1> nextBitmap;
        auto properties = D2D1::BitmapProperties1(D2D1_BITMAP_OPTIONS_TARGET,
            D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM, D2D1_ALPHA_MODE_PREMULTIPLIED), 96, 96);
        if (SUCCEEDED(hr)) hr = drawing->CreateBitmapFromDxgiSurface(surface.Get(), &properties, &nextBitmap);
        if (FAILED(hr)) return hr;
        DXGI_SWAP_CHAIN_DESC1 chain{};
        chain.Width = w; chain.Height = h; chain.Format = description.Format;
        chain.SampleDesc.Count = 1; chain.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
        chain.BufferCount = 2; chain.Scaling = DXGI_SCALING_STRETCH;
        chain.SwapEffect = DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL;
        chain.AlphaMode = DXGI_ALPHA_MODE_PREMULTIPLIED;
        ComPtr<IDXGISwapChain1> nextChain;
        hr = dxgi->CreateSwapChainForComposition(device.Get(), &chain, nullptr, &nextChain);
        if (SUCCEEDED(hr)) hr = visual->SetContent(nextChain.Get());
        if (SUCCEEDED(hr)) hr = composition->Commit();
        if (FAILED(hr)) return hr;
        drawing->SetTarget(nextBitmap.Get());
        texture = nextTexture; bitmap = nextBitmap; swapChain = nextChain;
        width = w; height = h;
        return S_OK;
    }

    HRESULT present() {
        ComPtr<ID3D11Texture2D> back;
        HRESULT hr = swapChain->GetBuffer(0, IID_PPV_ARGS(&back));
        if (FAILED(hr)) return hr;
        commands->CopyResource(back.Get(), texture.Get());
        return swapChain->Present(0, 0);
    }

    HRESULT wait() {
        commands->End(fence.Get());
        commands->Flush();
        const ULONGLONG deadline = GetTickCount64() + 2000;
        HRESULT hr;
        while ((hr = commands->GetData(fence.Get(), nullptr, 0, D3D11_ASYNC_GETDATA_DONOTFLUSH)) == S_FALSE) {
            if (GetTickCount64() >= deadline) return HRESULT_FROM_WIN32(ERROR_TIMEOUT);
            Sleep(0);
        }
        return hr;
    }

    HRESULT copyPixels(void* output, size_t bytes) {
        if (!texture || !output || bytes != size_t(width) * height * 4) return E_INVALIDARG;
        D3D11_TEXTURE2D_DESC description{};
        texture->GetDesc(&description);
        description.Usage = D3D11_USAGE_STAGING;
        description.BindFlags = 0; description.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
        ComPtr<ID3D11Texture2D> staging;
        HRESULT hr = device->CreateTexture2D(&description, nullptr, &staging);
        if (FAILED(hr)) return hr;
        commands->CopyResource(staging.Get(), texture.Get());
        hr = wait();
        if (FAILED(hr)) return hr;
        D3D11_MAPPED_SUBRESOURCE mapped{};
        hr = commands->Map(staging.Get(), 0, D3D11_MAP_READ, D3D11_MAP_FLAG_DO_NOT_WAIT, &mapped);
        if (FAILED(hr)) return hr;
        for (UINT row = 0; row < height; ++row)
            std::memcpy(static_cast<unsigned char*>(output) + size_t(row) * width * 4,
                        static_cast<unsigned char*>(mapped.pData) + size_t(row) * mapped.RowPitch, size_t(width) * 4);
        commands->Unmap(staging.Get(), 0);
        return S_OK;
    }
};
