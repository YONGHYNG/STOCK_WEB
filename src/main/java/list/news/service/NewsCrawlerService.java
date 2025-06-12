package list.news.service;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Service
public class NewsCrawlerService {

    public List<String> getPopularNewsTitles() {
        List<String> titles = new ArrayList<>();

        try {
            Document doc = Jsoup.connect("https://news.einfomax.co.kr/news/articleList.html?view_type=sm").get();

            //인기 뉴스 영역
            Elements links = doc.select("div#skin-15 div.item > a");

            for(Element link : links) {
                String fullTitle = link.text();
                String cleanedTitle = fullTitle.replaceFirst("^[0-9]{1,2}\\.\\s*", "");
                titles.add(cleanedTitle);
            }
        } catch (IOException e) {
            e.printStackTrace();
        }

        return titles;
    }

}
