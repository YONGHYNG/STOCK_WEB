package list.report.service;

import list.report.dto.MarketItem;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.select.Elements;
import org.jsoup.nodes.Element;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Service
public class MarketService {

    public List<MarketItem> fetchTitles() {
        List<MarketItem> results = new ArrayList<>();

        try {
            String url = "https://finance.daum.net/investment/stock_market";
            Document doc = Jsoup.connect(url)
                    .userAgent("Mozilla/5.0") // User-Agent 설정 필수
                    .get();

            Elements titleElements = doc.select("a.tit");

            for (Element titleEl : titleElements) {
                String title = titleEl.text().trim();
                if (!title.isEmpty()) {
                    results.add(new MarketItem(title));
                }
            }

        } catch (IOException e) {
            e.printStackTrace();
        }

        return results;
    }
}

