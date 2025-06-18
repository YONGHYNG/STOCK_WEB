package list.headline.service;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class IndexService {
    public List<Map<String, String>> getIndices() throws IOException {
        String url = "https://news.einfomax.co.kr/news/articleList.html?view_type=sm";
        Document doc = Jsoup.connect(url).get();
        List<Map<String, String>> indices = new ArrayList<>();

        Elements items = doc.select("#ticker #data .container .item");

        for (Element item : items) {
            Elements spans = item.select("span");

            if (spans.size() >= 2) {
                Map<String, String> index = new HashMap<>();
                index.put("name", spans.get(0).text());   // KOSPI
                index.put("value", spans.get(1).text());  // 2,970.46 ▲ 20.16 (0.68%)
                indices.add(index);
            }
        }

        return indices;
    }
}
