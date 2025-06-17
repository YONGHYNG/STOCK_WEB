package list.headline;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.io.IOException;

@Service
public class  IndexService {

    public String getIndexHtml() throws IOException {
        String url = "https://news.einfomax.co.kr/news/articleList.html?view_type=sm";
        Document doc = Jsoup.connect(url).get();

        StringBuilder htmlBuilder = new StringBuilder();

        // #ticker > #data > .container > .item 선택
        Elements items = doc.select("#ticker #data .container .item");

        for (Element item : items) {
            String uid = item.attr("uid");

            Elements spans = item.select("span");
            if (spans.size() >= 2) {
                String indexName = spans.get(0).text();    // 예: KOSPI, NASDAQ
                String indexValue = spans.get(1).text();   // 예: 2,946.66 ▲ 52.04 (1.80%)

                htmlBuilder.append("<div class=\"item\" uid=\"")
                        .append(uid)
                        .append("\">")
                        .append(indexName)
                        .append(" : ")
                        .append(indexValue)
                        .append("</div>\n");
            }
        }

        return htmlBuilder.toString();
    }
}
