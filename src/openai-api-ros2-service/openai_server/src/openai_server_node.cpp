#include <rclcpp/rclcpp.hpp>
#include <curl/curl.h>
#include <nlohmann/json.hpp>

// Korrekte automatische Header-Datei für OpenaiServer.srv
#include "openai_server_interfaces/srv/openai_server.hpp"

using std::placeholders::_1;
using std::placeholders::_2;
using json = nlohmann::json;

// Neuer korrekter Name basierend auf OpenaiServer.srv
using OpenaiServerSrv = openai_server_interfaces::srv::OpenaiServer;

class OpenaiServerNode : public rclcpp::Node {
public:
    OpenaiServerNode() : Node("openai_server") {
        this->declare_parameter<std::string>("openai_api_key", "");
        this->get_parameter("openai_api_key", api_key_);
        this->declare_parameter<std::string>("openai_model", "gpt-4o");
        this->get_parameter("openai_model", model_);


        if (api_key_.empty()) {
            RCLCPP_ERROR(this->get_logger(), "API key not set. Use --ros-args -p openai_api_key:=<key>");
            rclcpp::shutdown();
            return;
        }

        RCLCPP_INFO(this->get_logger(), "Using OpenAI model: %s", model_.c_str());


        service_ = this->create_service<OpenaiServerSrv>(
            "openai_ask",
            std::bind(&OpenaiServerNode::handle_request, this, _1, _2)
        );

        RCLCPP_INFO(this->get_logger(), "OpenAI Server is ready.");
    }

private:
    std::string api_key_;
    rclcpp::Service<OpenaiServerSrv>::SharedPtr service_;
    std::vector<std::pair<std::string, std::string>> conversation_history_;
    std::string model_;



    static size_t write_callback(void* contents, size_t size, size_t nmemb, std::string* output) {
        size_t totalSize = size * nmemb;
        output->append((char*)contents, totalSize);
        return totalSize;
    }

    std::string build_conversation_json(const std::string& prompt, const std::string& pre_prompt) {
        json messages = json::array();

        // Alte Konversation (falls vorhanden)
        for (const auto& [role, content] : conversation_history_) {
            messages.push_back({{"role", role}, {"content", content}});
        }

        // Falls ein pre_prompt gesetzt ist, als System-Nachricht voranstellen
        if (!pre_prompt.empty()) {
            messages.push_back({{"role", "system"}, {"content", pre_prompt}});
        }

        // Neue User-Eingabe
        messages.push_back({{"role", "user"}, {"content", prompt}});

        json request_body = {
            {"model", model_},
            {"messages", messages}
        };

        return request_body.dump();
    }



    std::string query_openai(const std::string& prompt, const std::string& pre_prompt) {
        CURL* curl;
        CURLcode res;
        std::string response_string;

        curl_global_init(CURL_GLOBAL_ALL);
        curl = curl_easy_init();

        if (curl) {
            std::string data = build_conversation_json(prompt, pre_prompt);

            struct curl_slist* headers = NULL;
            headers = curl_slist_append(headers, "Content-Type: application/json");
            headers = curl_slist_append(headers, ("Authorization: Bearer " + api_key_).c_str());

            curl_easy_setopt(curl, CURLOPT_URL, "https://api.openai.com/v1/chat/completions");
            curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
            curl_easy_setopt(curl, CURLOPT_POSTFIELDS, data.c_str());
            curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
            curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_string);

            res = curl_easy_perform(curl);
            if (res != CURLE_OK) {
                RCLCPP_ERROR(this->get_logger(), "Request failed: %s", curl_easy_strerror(res));
            }

            curl_easy_cleanup(curl);
            curl_slist_free_all(headers);
        }

        curl_global_cleanup();
        return response_string;
    }


    void handle_request(
        const std::shared_ptr<OpenaiServerSrv::Request> request,
        std::shared_ptr<OpenaiServerSrv::Response> response)
    {
        const std::string& user_input = request->prompt;
        const bool reset = request->reset_conversation;
        const std::string& pre_prompt = request->pre_prompt;

        RCLCPP_INFO(this->get_logger(), "Prompt received: %s", user_input.c_str());
        RCLCPP_INFO(this->get_logger(), "Reset: %s | PrePrompt: %s",
                    reset ? "true" : "false", pre_prompt.empty() ? "(none)" : pre_prompt.c_str());

        if (reset) {
            conversation_history_.clear();
        }

        // Prompt zur Historie hinzufügen (User-Eingabe)
        conversation_history_.emplace_back("user", user_input);

        // Anfrage stellen (Prompt + PrePrompt)
        std::string api_response = query_openai(user_input, pre_prompt);

        try {
            auto json_response = json::parse(api_response);
            std::string assistant_reply = json_response["choices"][0]["message"]["content"];

            // Antwort auch zur History hinzufügen
            conversation_history_.emplace_back("assistant", assistant_reply);

            response->response = assistant_reply;
        } catch (const std::exception& e) {
            RCLCPP_ERROR(this->get_logger(), "JSON parse error: %s", e.what());
            response->response = "Fehler beim Verarbeiten der OpenAI-Antwort.";
        }
    }


};

// Main
int main(int argc, char **argv) {
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<OpenaiServerNode>());
    rclcpp::shutdown();
    return 0;
}

