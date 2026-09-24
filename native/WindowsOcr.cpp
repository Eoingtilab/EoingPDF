#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Globalization.h>
#include <winrt/Windows.Graphics.Imaging.h>
#include <winrt/Windows.Media.Ocr.h>
#include <winrt/Windows.Storage.h>
#include <winrt/Windows.Storage.Streams.h>
#include <winrt/Windows.Data.Json.h>
#include <fstream>
#include <iostream>
#include <string>

int wmain(int argc, wchar_t** argv) {
    try {
        winrt::init_apartment(winrt::apartment_type::multi_threaded);
        using namespace winrt::Windows::Media::Ocr;
        if (argc == 2 && std::wstring(argv[1]) == L"--languages") {
            for (auto language : OcrEngine::AvailableRecognizerLanguages())
                std::cout << winrt::to_string(language.LanguageTag()) << "\n";
            return 0;
        }
        bool jsonOutput = argc == 4 && std::wstring(argv[3]) == L"--json";
        if (argc != 3 && !jsonOutput) return 2;
        auto engine = OcrEngine::TryCreateFromLanguage(winrt::Windows::Globalization::Language(L"ko"));
        if (!engine) engine = OcrEngine::TryCreateFromUserProfileLanguages();
        if (!engine) { std::cerr << "OCR_LANGUAGE_UNAVAILABLE"; return 3; }
        auto file = winrt::Windows::Storage::StorageFile::GetFileFromPathAsync(argv[1]).get();
        auto stream = file.OpenAsync(winrt::Windows::Storage::FileAccessMode::Read).get();
        auto decoder = winrt::Windows::Graphics::Imaging::BitmapDecoder::CreateAsync(stream).get();
        auto bitmap = decoder.GetSoftwareBitmapAsync(
            winrt::Windows::Graphics::Imaging::BitmapPixelFormat::Bgra8,
            winrt::Windows::Graphics::Imaging::BitmapAlphaMode::Premultiplied).get();
        if (bitmap.PixelWidth() > OcrEngine::MaxImageDimension() || bitmap.PixelHeight() > OcrEngine::MaxImageDimension())
            return 4;
        auto result = engine.RecognizeAsync(bitmap).get();
        std::ofstream output(argv[2], std::ios::binary);
        if (!output) return 5;
        if (jsonOutput) {
            using namespace winrt::Windows::Data::Json;
            JsonObject root;
            root.Insert(L"width", JsonValue::CreateNumberValue(bitmap.PixelWidth()));
            root.Insert(L"height", JsonValue::CreateNumberValue(bitmap.PixelHeight()));
            JsonArray lines;
            for (auto line : result.Lines()) {
                JsonObject row;
                row.Insert(L"text", JsonValue::CreateStringValue(line.Text()));
                JsonArray words;
                for (auto word : line.Words()) {
                    JsonObject entry;
                    auto bounds = word.BoundingRect();
                    entry.Insert(L"text", JsonValue::CreateStringValue(word.Text()));
                    JsonArray box;
                    for (double value : { double(bounds.X), double(bounds.Y), double(bounds.Width), double(bounds.Height) })
                        box.Append(JsonValue::CreateNumberValue(value));
                    entry.Insert(L"box", box);
                    words.Append(entry);
                }
                row.Insert(L"words", words);
                lines.Append(row);
            }
            root.Insert(L"lines", lines);
            output << winrt::to_string(root.Stringify());
        } else {
            for (auto line : result.Lines()) output << winrt::to_string(line.Text()) << "\n";
        }
        output.close();
        return output ? 0 : 5;
    } catch (winrt::hresult_error const& error) {
        std::cerr << winrt::to_string(error.message());
        return 1;
    } catch (std::exception const& error) {
        std::cerr << error.what();
        return 1;
    }
}
